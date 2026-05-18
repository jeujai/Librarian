"""
Property-based tests for dataset validation.

# Feature: medical-knowledge-finetuning, Property 16: Dataset validation
#   correctly partitions pairs
# Feature: medical-knowledge-finetuning, Property 17: Quality warning
#   threshold

Validates: Requirements 11.1, 11.2, 11.3, 11.5
"""

from __future__ import annotations

import asyncio
import logging
import string
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.models import (
    VALID_STRATEGIES,
    InstructionTuningPair,
    PairMetadata,
    ValidationResult,
)
from multimodal_librarian.ml.training_data_generator import (
    _MIN_QUALITY_PASS_RATE,
    _MIN_RESPONSE_TOKENS,
    TrainingDataGenerator,
    _count_tokens,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum number of whitespace-separated tokens to satisfy the 50-token check
_LONG_WORD = "medical"
_LONG_RESPONSE = " ".join([_LONG_WORD] * (_MIN_RESPONSE_TOKENS + 10))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_generator(*, ner_returns: bool = True) -> TrainingDataGenerator:
    """Create a TrainingDataGenerator with a mock NER extractor.

    Args:
        ner_returns: If ``True`` the mock NER extractor reports that a
            UMLS concept was found.  If ``False`` it reports none found.
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


def _make_generator_no_ner() -> TrainingDataGenerator:
    """Create a TrainingDataGenerator with no NER extractor (None).

    When NER is None, ``_check_umls_concept`` returns True by default,
    so the UMLS concept check is effectively skipped.
    """
    return TrainingDataGenerator(
        neo4j_client=None,  # type: ignore[arg-type]
        vector_client=None,  # type: ignore[arg-type]
        rag_service=None,  # type: ignore[arg-type]
        umls_client=None,  # type: ignore[arg-type]
        relationship_traverser=None,  # type: ignore[arg-type]
        ner_extractor=None,  # type: ignore[arg-type]
    )


def _make_pair(
    *,
    instruction: str = "What is aspirin?",
    context: str = "Aspirin is a medication.",
    response: str = _LONG_RESPONSE,
    strategy: str = "kg",
    confidence: float = 0.9,
) -> InstructionTuningPair:
    """Build an InstructionTuningPair with sensible defaults."""
    return InstructionTuningPair(
        instruction=instruction,
        context=context,
        response=response,
        metadata=PairMetadata(
            strategy=strategy,
            source_concepts=["C0000001"],
            confidence_score=confidence,
        ),
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


def _non_empty_text(
    min_size: int = 1,
    max_size: int = 200,
) -> st.SearchStrategy[str]:
    """Non-empty text with at least one non-ws char."""
    alphabet = string.ascii_letters + string.digits + " "
    return st.text(
        alphabet=alphabet,
        min_size=min_size,
        max_size=max_size,
    ).filter(lambda s: len(s.strip()) >= min_size)


def _long_response_text() -> st.SearchStrategy[str]:
    """Response with >= 50 whitespace-separated tokens."""
    return st.integers(
        min_value=_MIN_RESPONSE_TOKENS,
        max_value=_MIN_RESPONSE_TOKENS + 50,
    ).map(lambda n: " ".join(["token"] * n))


def _short_response_text() -> st.SearchStrategy[str]:
    """Response with < 50 tokens (but non-empty)."""
    return st.integers(
        min_value=1,
        max_value=_MIN_RESPONSE_TOKENS - 1,
    ).map(lambda n: " ".join(["word"] * n))


def _valid_pair_strategy() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair that should pass all validation checks.

    - Non-empty instruction, context, and response
    - Response has >= 50 tokens
    - NER check is handled by the mock (returns True)
    """
    return st.builds(
        _make_pair,
        instruction=_non_empty_text(min_size=5),
        context=_non_empty_text(min_size=5),
        response=_long_response_text(),
        strategy=st.sampled_from(list(VALID_STRATEGIES)),
        confidence=st.floats(
            min_value=0.0,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )


def _invalid_pair_strategy() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a pair that fails at least one validation check.

    We pick one of three failure modes:
    1. Empty/whitespace-only instruction
    2. Empty/whitespace-only context
    3. Response too short (< 50 tokens)

    Because InstructionTuningPair has min_length=1 on instruction/context/
    response, we use whitespace-only strings (which pass Pydantic but fail
    the strip() check in validate_dataset).
    """
    # Whitespace-only strings that pass Pydantic min_length=1 but fail strip()
    whitespace_only = st.sampled_from([" ", "  ", "\t", "\n", " \t\n "])

    empty_instruction = st.builds(
        _make_pair,
        instruction=whitespace_only,
        context=_non_empty_text(min_size=5),
        response=_long_response_text(),
        strategy=st.sampled_from(list(VALID_STRATEGIES)),
    )

    empty_context = st.builds(
        _make_pair,
        instruction=_non_empty_text(min_size=5),
        context=whitespace_only,
        response=_long_response_text(),
        strategy=st.sampled_from(list(VALID_STRATEGIES)),
    )

    short_response = st.builds(
        _make_pair,
        instruction=_non_empty_text(min_size=5),
        context=_non_empty_text(min_size=5),
        response=_short_response_text(),
        strategy=st.sampled_from(list(VALID_STRATEGIES)),
    )

    return st.one_of(empty_instruction, empty_context, short_response)


# ---------------------------------------------------------------------------
# Property 16: Dataset validation correctly partitions pairs
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestDatasetValidationPartitioning:
    """Property 16: Dataset validation correctly partitions pairs.

    For any list of InstructionTuningPairs, validation SHALL partition
    them into accepted and rejected sets such that:

    (a) every accepted pair has response length >= 50 tokens, non-empty
        instruction, non-empty context, valid JSON structure, and at
        least one NER-recognised UMLS concept in the response;

    (b) every rejected pair fails at least one of these checks and has
        a non-empty rejection reason.

    Validates: Requirements 11.1, 11.2, 11.3
    """

    # ------------------------------------------------------------------
    # Core property: accepted pairs meet ALL quality checks
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_valid_pair_strategy(), min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_accepted_pairs_meet_all_checks(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Every accepted pair has non-empty instruction, non-empty
        context, response >= 50 tokens, and passes the UMLS concept
        check.
        """
        gen = _make_generator(ner_returns=True)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset(pairs)
        )

        for pair in result.accepted:
            assert pair.instruction.strip(), (
                "Accepted pair has empty instruction"
            )
            assert pair.context.strip(), (
                "Accepted pair has empty context"
            )
            assert _count_tokens(pair.response) >= _MIN_RESPONSE_TOKENS, (
                f"Accepted pair has response with only "
                f"{_count_tokens(pair.response)} tokens "
                f"(min {_MIN_RESPONSE_TOKENS})"
            )

    # ------------------------------------------------------------------
    # Core property: rejected pairs fail at least one check with reason
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_invalid_pair_strategy(), min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_rejected_pairs_fail_at_least_one_check(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Every rejected pair fails at least one quality check and has
        a non-empty rejection reason recorded.
        """
        gen = _make_generator(ner_returns=True)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset(pairs)
        )

        # All deliberately invalid pairs should be rejected
        assert len(result.rejected) == len(pairs), (
            f"Expected all {len(pairs)} invalid pairs to be rejected, "
            f"but {len(result.accepted)} were accepted"
        )

        # Each rejected pair must have at least one rejection reason
        for pair in result.rejected:
            key = pair.instruction[:100]
            assert key in result.rejection_reasons, (
                f"Rejected pair missing from rejection_reasons: "
                f"{pair.instruction[:50]!r}"
            )
            reasons = result.rejection_reasons[key]
            assert len(reasons) >= 1, (
                f"Rejected pair has empty rejection reasons: "
                f"{pair.instruction[:50]!r}"
            )
            # Verify each reason is a non-empty string
            for reason in reasons:
                assert isinstance(reason, str) and reason.strip(), (
                    f"Rejection reason is empty or not a string: {reason!r}"
                )

    # ------------------------------------------------------------------
    # Mixed input: partition is exhaustive and disjoint
    # ------------------------------------------------------------------

    @given(
        valid=st.lists(_valid_pair_strategy(), min_size=0, max_size=10),
        invalid=st.lists(_invalid_pair_strategy(), min_size=0, max_size=10),
    )
    @settings(max_examples=100, deadline=None)
    def test_partition_is_exhaustive_and_disjoint(
        self,
        valid: List[InstructionTuningPair],
        invalid: List[InstructionTuningPair],
    ) -> None:
        """accepted ∪ rejected == input, and accepted ∩ rejected == ∅."""
        all_pairs = valid + invalid
        assume(len(all_pairs) > 0)

        gen = _make_generator(ner_returns=True)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset(all_pairs)
        )

        # Exhaustive: every input pair appears in exactly one partition
        assert result.total == len(all_pairs), (
            f"total ({result.total}) != input length ({len(all_pairs)})"
        )
        assert len(result.accepted) + len(result.rejected) == len(all_pairs), (
            f"accepted ({len(result.accepted)}) + "
            f"rejected ({len(result.rejected)}) != "
            f"input ({len(all_pairs)})"
        )

        # Disjoint: no pair appears in both partitions
        accepted_ids = {id(p) for p in result.accepted}
        rejected_ids = {id(p) for p in result.rejected}
        assert accepted_ids.isdisjoint(rejected_ids), (
            "A pair appears in both accepted and rejected"
        )

    # ------------------------------------------------------------------
    # NER failure mode: pairs rejected when no UMLS concept found
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_valid_pair_strategy(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_no_umls_concept_causes_rejection(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """When NER finds no UMLS concepts, otherwise-valid pairs are
        rejected with reason 'no_umls_concept_in_response'.
        """
        gen = _make_generator(ner_returns=False)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset(pairs)
        )

        # All pairs should be rejected because NER returns no concepts
        assert len(result.rejected) == len(pairs), (
            f"Expected all {len(pairs)} pairs rejected (no UMLS concept), "
            f"but {len(result.accepted)} were accepted"
        )

        for pair in result.rejected:
            key = pair.instruction[:100]
            reasons = result.rejection_reasons.get(key, [])
            assert any("no_umls_concept" in r for r in reasons), (
                f"Expected 'no_umls_concept_in_response' reason for "
                f"{pair.instruction[:50]!r}, got {reasons}"
            )

    # ------------------------------------------------------------------
    # NER unavailable: pairs accepted by default
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_valid_pair_strategy(), min_size=1, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_ner_unavailable_accepts_by_default(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """When NER extractor is None, the UMLS concept check is
        skipped and otherwise-valid pairs are accepted.
        """
        gen = _make_generator_no_ner()
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset(pairs)
        )

        assert len(result.accepted) == len(pairs), (
            f"Expected all {len(pairs)} pairs accepted (NER unavailable), "
            f"but {len(result.rejected)} were rejected"
        )

    # ------------------------------------------------------------------
    # Pass rate is correctly computed
    # ------------------------------------------------------------------

    @given(
        valid=st.lists(_valid_pair_strategy(), min_size=0, max_size=10),
        invalid=st.lists(_invalid_pair_strategy(), min_size=0, max_size=10),
    )
    @settings(max_examples=100, deadline=None)
    def test_pass_rate_is_correct(
        self,
        valid: List[InstructionTuningPair],
        invalid: List[InstructionTuningPair],
    ) -> None:
        """pass_rate == len(accepted) / total for non-empty inputs."""
        all_pairs = valid + invalid
        assume(len(all_pairs) > 0)

        gen = _make_generator(ner_returns=True)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset(all_pairs)
        )

        expected_rate = len(result.accepted) / result.total
        assert abs(result.pass_rate - expected_rate) < 1e-9, (
            f"pass_rate {result.pass_rate} != "
            f"expected {expected_rate}"
        )

    # ------------------------------------------------------------------
    # Empty input produces empty result
    # ------------------------------------------------------------------

    def test_empty_input_returns_empty_result(self) -> None:
        """Validating an empty list returns an empty ValidationResult."""
        gen = _make_generator(ner_returns=True)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset([])
        )

        assert result.accepted == []
        assert result.rejected == []
        assert result.total == 0
        assert result.pass_rate == 0.0

    # ------------------------------------------------------------------
    # Boundary: response with exactly 50 tokens is accepted
    # ------------------------------------------------------------------

    def test_response_with_exactly_min_tokens_is_accepted(self) -> None:
        """A response with exactly _MIN_RESPONSE_TOKENS tokens passes
        the length check.
        """
        exact_response = " ".join(["word"] * _MIN_RESPONSE_TOKENS)
        assert _count_tokens(exact_response) == _MIN_RESPONSE_TOKENS

        pair = _make_pair(response=exact_response)
        gen = _make_generator(ner_returns=True)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset([pair])
        )

        assert len(result.accepted) == 1
        assert len(result.rejected) == 0

    # ------------------------------------------------------------------
    # Boundary: response with 49 tokens is rejected
    # ------------------------------------------------------------------

    def test_response_with_one_below_min_tokens_is_rejected(self) -> None:
        """A response with _MIN_RESPONSE_TOKENS - 1 tokens fails the
        length check.
        """
        short_response = " ".join(["word"] * (_MIN_RESPONSE_TOKENS - 1))
        assert _count_tokens(short_response) == _MIN_RESPONSE_TOKENS - 1

        pair = _make_pair(response=short_response)
        gen = _make_generator(ner_returns=True)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset([pair])
        )

        assert len(result.rejected) == 1
        key = pair.instruction[:100]
        reasons = result.rejection_reasons[key]
        assert any("response_too_short" in r for r in reasons)

    # ------------------------------------------------------------------
    # Multiple failures are all recorded
    # ------------------------------------------------------------------

    def test_multiple_failures_recorded(self) -> None:
        """A pair that fails multiple checks has all reasons recorded."""
        pair = _make_pair(
            instruction=" ",   # whitespace-only
            context="\t",      # whitespace-only
            response="short",  # < 50 tokens
        )
        gen = _make_generator(ner_returns=True)
        result: ValidationResult = asyncio.get_event_loop().run_until_complete(
            gen.validate_dataset([pair])
        )

        assert len(result.rejected) == 1
        key = pair.instruction[:100]
        reasons = result.rejection_reasons[key]
        # Should have at least: empty_instruction, empty_context, response_too_short
        assert any("empty_instruction" in r for r in reasons), (
            f"Missing 'empty_instruction' in {reasons}"
        )
        assert any("empty_context" in r for r in reasons), (
            f"Missing 'empty_context' in {reasons}"
        )
        assert any("response_too_short" in r for r in reasons), (
            f"Missing 'response_too_short' in {reasons}"
        )


# ---------------------------------------------------------------------------
# Helper: check quality warning threshold
# ---------------------------------------------------------------------------

_LOGGER_NAME = (
    "multimodal_librarian.ml.training_data_generator"
)


def _check_quality_warning(
    pass_rate: float,
    logger_instance: logging.Logger,
) -> None:
    """Replicate the quality warning check from generate().

    This mirrors the exact logic in ``generate()`` so that we
    can test the warning threshold in isolation without running
    the full generation pipeline.
    """
    if pass_rate < _MIN_QUALITY_PASS_RATE:
        logger_instance.warning(
            "Training data: Quality pass rate %.1f%% is below "
            "%.0f%% threshold. Review generation strategy "
            "parameters.",
            pass_rate * 100,
            _MIN_QUALITY_PASS_RATE * 100,
        )


class _WarningCollector(logging.Handler):
    """Logging handler that collects WARNING+ records.

    Used instead of ``caplog`` in ``@given`` tests because
    Hypothesis does not reset function-scoped fixtures between
    generated inputs.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: List[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno >= logging.WARNING:
            self.records.append(record)

    @property
    def messages(self) -> List[str]:
        return [r.getMessage() for r in self.records]


# ---------------------------------------------------------------------------
# Property 17: Quality warning threshold
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestQualityWarningThreshold:
    """Property 17: Quality warning threshold.

    For any validation result where the pass rate (accepted / total)
    falls below 0.70, a warning SHALL be logged. When pass rate is
    >= 0.70, no warning SHALL be logged.

    Validates: Requirements 11.5
    """

    # ------------------------------------------------------------------
    # Core property: warning logged when pass rate < 0.70
    # ------------------------------------------------------------------

    @given(
        pass_rate=st.floats(
            min_value=0.0,
            max_value=_MIN_QUALITY_PASS_RATE,
            exclude_max=True,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_warning_logged_when_below_threshold(
        self,
        pass_rate: float,
    ) -> None:
        """A warning is logged when pass_rate < 0.70."""
        test_logger = logging.getLogger(_LOGGER_NAME)
        handler = _WarningCollector()
        test_logger.addHandler(handler)
        try:
            _check_quality_warning(pass_rate, test_logger)
            msgs = handler.messages
            assert len(msgs) >= 1, (
                f"Expected a warning for "
                f"pass_rate={pass_rate:.4f} "
                f"(< {_MIN_QUALITY_PASS_RATE}), "
                f"but none was logged"
            )
            assert any("threshold" in m for m in msgs), (
                f"Warning should mention 'threshold', "
                f"got: {msgs}"
            )
        finally:
            test_logger.removeHandler(handler)

    # ------------------------------------------------------------------
    # Core property: no warning when pass rate >= 0.70
    # ------------------------------------------------------------------

    @given(
        pass_rate=st.floats(
            min_value=_MIN_QUALITY_PASS_RATE,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_no_warning_when_at_or_above_threshold(
        self,
        pass_rate: float,
    ) -> None:
        """No warning is logged when pass_rate >= 0.70."""
        test_logger = logging.getLogger(_LOGGER_NAME)
        handler = _WarningCollector()
        test_logger.addHandler(handler)
        try:
            _check_quality_warning(pass_rate, test_logger)
            quality_msgs = [
                m for m in handler.messages
                if "Quality pass rate" in m
            ]
            assert len(quality_msgs) == 0, (
                f"Expected no quality warning for "
                f"pass_rate={pass_rate:.4f} "
                f"(>= {_MIN_QUALITY_PASS_RATE}), "
                f"but got: {quality_msgs}"
            )
        finally:
            test_logger.removeHandler(handler)

    # ------------------------------------------------------------------
    # Property via validate_dataset: low pass rate → warning
    # ------------------------------------------------------------------

    @given(
        valid_count=st.integers(min_value=0, max_value=6),
        invalid_count=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=100, deadline=None)
    def test_validate_low_pass_rate_triggers_warning(
        self,
        valid_count: int,
        invalid_count: int,
    ) -> None:
        """When validate_dataset produces pass rate < 0.70,
        the quality warning check fires.
        """
        total = valid_count + invalid_count
        assume(total > 0)
        expected_rate = valid_count / total
        assume(expected_rate < _MIN_QUALITY_PASS_RATE)

        valid_pairs = [
            _make_pair(
                instruction=f"Valid question {i}?",
                context=f"Valid context {i}.",
                response=_LONG_RESPONSE,
            )
            for i in range(valid_count)
        ]
        invalid_pairs = [
            _make_pair(
                instruction=f"Invalid question {i}?",
                context=f"Invalid context {i}.",
                response="short",
            )
            for i in range(invalid_count)
        ]

        all_pairs = valid_pairs + invalid_pairs
        gen = _make_generator(ner_returns=True)
        loop = asyncio.get_event_loop()
        result: ValidationResult = (
            loop.run_until_complete(
                gen.validate_dataset(all_pairs)
            )
        )

        assert result.pass_rate < _MIN_QUALITY_PASS_RATE

        test_logger = logging.getLogger(_LOGGER_NAME)
        handler = _WarningCollector()
        test_logger.addHandler(handler)
        try:
            _check_quality_warning(
                result.pass_rate, test_logger,
            )
            assert len(handler.messages) >= 1, (
                f"Expected warning for "
                f"pass_rate={result.pass_rate:.4f}"
            )
        finally:
            test_logger.removeHandler(handler)

    # ------------------------------------------------------------------
    # Property via validate_dataset: high pass rate → no warning
    # ------------------------------------------------------------------

    @given(
        valid_count=st.integers(min_value=7, max_value=20),
        invalid_count=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=100, deadline=None)
    def test_validate_high_pass_rate_no_warning(
        self,
        valid_count: int,
        invalid_count: int,
    ) -> None:
        """When validate_dataset produces pass rate >= 0.70,
        no quality warning is emitted.
        """
        total = valid_count + invalid_count
        assume(total > 0)
        expected_rate = valid_count / total
        assume(expected_rate >= _MIN_QUALITY_PASS_RATE)

        valid_pairs = [
            _make_pair(
                instruction=f"Valid question {i}?",
                context=f"Valid context {i}.",
                response=_LONG_RESPONSE,
            )
            for i in range(valid_count)
        ]
        invalid_pairs = [
            _make_pair(
                instruction=f"Invalid question {i}?",
                context=f"Invalid context {i}.",
                response="short",
            )
            for i in range(invalid_count)
        ]

        all_pairs = valid_pairs + invalid_pairs
        gen = _make_generator(ner_returns=True)
        loop = asyncio.get_event_loop()
        result: ValidationResult = (
            loop.run_until_complete(
                gen.validate_dataset(all_pairs)
            )
        )

        assert result.pass_rate >= _MIN_QUALITY_PASS_RATE

        test_logger = logging.getLogger(_LOGGER_NAME)
        handler = _WarningCollector()
        test_logger.addHandler(handler)
        try:
            _check_quality_warning(
                result.pass_rate, test_logger,
            )
            quality_msgs = [
                m for m in handler.messages
                if "Quality pass rate" in m
            ]
            assert len(quality_msgs) == 0, (
                f"Expected no warning for "
                f"pass_rate={result.pass_rate:.4f}, "
                f"but got: {quality_msgs}"
            )
        finally:
            test_logger.removeHandler(handler)

    # ------------------------------------------------------------------
    # Boundary: pass rate exactly at threshold → no warning
    # ------------------------------------------------------------------

    def test_exact_threshold_no_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """pass_rate == 0.70 does NOT trigger a warning."""
        caplog.clear()
        test_logger = logging.getLogger(_LOGGER_NAME)
        with caplog.at_level(
            logging.WARNING, logger=test_logger.name,
        ):
            _check_quality_warning(
                _MIN_QUALITY_PASS_RATE, test_logger,
            )

        quality_msgs = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "Quality pass rate" in r.message
        ]
        assert len(quality_msgs) == 0, (
            f"pass_rate == {_MIN_QUALITY_PASS_RATE} should "
            f"NOT trigger a warning, "
            f"but got: {quality_msgs}"
        )

    # ------------------------------------------------------------------
    # Boundary: pass rate just below threshold → warning
    # ------------------------------------------------------------------

    def test_just_below_threshold_triggers_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """pass_rate just below 0.70 triggers a warning."""
        just_below = _MIN_QUALITY_PASS_RATE - 1e-9
        caplog.clear()
        test_logger = logging.getLogger(_LOGGER_NAME)
        with caplog.at_level(
            logging.WARNING, logger=test_logger.name,
        ):
            _check_quality_warning(
                just_below, test_logger,
            )

        warnings = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING
        ]
        assert len(warnings) >= 1, (
            f"pass_rate={just_below:.10f} (just below "
            f"{_MIN_QUALITY_PASS_RATE}) should trigger "
            f"a warning"
        )

    # ------------------------------------------------------------------
    # Boundary: pass rate 0.0 → warning
    # ------------------------------------------------------------------

    def test_zero_pass_rate_triggers_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A pass rate of 0.0 triggers a warning."""
        caplog.clear()
        test_logger = logging.getLogger(_LOGGER_NAME)
        with caplog.at_level(
            logging.WARNING, logger=test_logger.name,
        ):
            _check_quality_warning(0.0, test_logger)

        warnings = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING
        ]
        assert len(warnings) >= 1, (
            "pass_rate=0.0 should trigger a warning"
        )

    # ------------------------------------------------------------------
    # Boundary: pass rate 1.0 → no warning
    # ------------------------------------------------------------------

    def test_perfect_pass_rate_no_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A pass rate of 1.0 does NOT trigger a warning."""
        caplog.clear()
        test_logger = logging.getLogger(_LOGGER_NAME)
        with caplog.at_level(
            logging.WARNING, logger=test_logger.name,
        ):
            _check_quality_warning(1.0, test_logger)

        quality_msgs = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "Quality pass rate" in r.message
        ]
        assert len(quality_msgs) == 0, (
            "pass_rate=1.0 should NOT trigger a warning"
        )

    # ------------------------------------------------------------------
    # Integration: validate_dataset with all-invalid → warning fires
    # ------------------------------------------------------------------

    def test_all_invalid_pairs_triggers_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When every pair is rejected, pass_rate is 0.0 and
        the warning fires.
        """
        pairs = [
            _make_pair(
                instruction=f"Q{i}?",
                context=f"C{i}.",
                response="short",
            )
            for i in range(5)
        ]
        gen = _make_generator(ner_returns=True)
        result: ValidationResult = (
            asyncio.get_event_loop().run_until_complete(
                gen.validate_dataset(pairs)
            )
        )

        assert result.pass_rate == 0.0
        assert len(result.rejected) == 5

        caplog.clear()
        test_logger = logging.getLogger(_LOGGER_NAME)
        with caplog.at_level(
            logging.WARNING, logger=test_logger.name,
        ):
            _check_quality_warning(
                result.pass_rate, test_logger,
            )

        warnings = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING
        ]
        assert len(warnings) >= 1

    # ------------------------------------------------------------------
    # Integration: validate_dataset with all-valid → no warning
    # ------------------------------------------------------------------

    def test_all_valid_pairs_no_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """When every pair is accepted, pass_rate is 1.0 and
        no warning fires.
        """
        pairs = [
            _make_pair(
                instruction=f"Valid question {i}?",
                context=f"Valid context {i}.",
                response=_LONG_RESPONSE,
            )
            for i in range(5)
        ]
        gen = _make_generator(ner_returns=True)
        result: ValidationResult = (
            asyncio.get_event_loop().run_until_complete(
                gen.validate_dataset(pairs)
            )
        )

        assert result.pass_rate == 1.0
        assert len(result.accepted) == 5

        caplog.clear()
        test_logger = logging.getLogger(_LOGGER_NAME)
        with caplog.at_level(
            logging.WARNING, logger=test_logger.name,
        ):
            _check_quality_warning(
                result.pass_rate, test_logger,
            )

        quality_msgs = [
            r.message
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "Quality pass rate" in r.message
        ]
        assert len(quality_msgs) == 0
