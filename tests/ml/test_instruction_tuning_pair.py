"""
Property-based tests for InstructionTuningPair.

# Feature: medical-knowledge-finetuning
# Property 1: Instruction tuning pair structural validity
# Property 18: JSONL round-trip serialization
# Property 19: Graceful handling of invalid JSONL lines

Validates: Requirements 1.6, 2.6, 4.4, 12.1–12.4
"""

import json
import logging
import logging.handlers
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.models import (
    VALID_STRATEGIES,
    InstructionTuningPair,
    PairMetadata,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies for generating valid model instances
# ---------------------------------------------------------------------------

def _non_empty_text() -> st.SearchStrategy[str]:
    """Generate non-empty strings with at least one non-whitespace character."""
    return st.text(min_size=1, max_size=500).filter(lambda s: s.strip())


def _confidence_score() -> st.SearchStrategy[float]:
    """Generate a float in [0.0, 1.0]."""
    return st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


def _strategy_name() -> st.SearchStrategy[str]:
    """Generate a valid strategy name."""
    return st.sampled_from(list(VALID_STRATEGIES))


def pair_metadata_strategy() -> st.SearchStrategy[PairMetadata]:
    """Generate a valid PairMetadata instance."""
    return st.builds(
        PairMetadata,
        strategy=_strategy_name(),
        source_concepts=st.lists(st.text(min_size=1, max_size=50), max_size=10),
        confidence_score=_confidence_score(),
        source_document=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
        chunk_ids=st.one_of(st.none(), st.lists(st.text(min_size=1, max_size=50), max_size=10)),
        relationship_chain=st.one_of(st.none(), st.text(min_size=1, max_size=300)),
    )


def instruction_tuning_pair_strategy() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a valid InstructionTuningPair instance."""
    return st.builds(
        InstructionTuningPair,
        instruction=_non_empty_text(),
        context=_non_empty_text(),
        response=_non_empty_text(),
        metadata=pair_metadata_strategy(),
    )


# ---------------------------------------------------------------------------
# Property 1: Instruction tuning pair structural validity
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestInstructionTuningPairStructuralValidity:
    """Property 1: Instruction tuning pair structural validity.

    For any InstructionTuningPair produced by any of the three generation
    strategies (KG, RAG, UMLS Reasoning), the pair SHALL have a non-empty
    instruction field, a non-empty context field, a non-empty response field,
    and a metadata object with a valid strategy value and a confidence_score
    between 0.0 and 1.0.
    """

    @given(pair=instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_instruction_is_non_empty(self, pair: InstructionTuningPair) -> None:
        """Instruction field must be a non-empty string."""
        assert isinstance(pair.instruction, str)
        assert len(pair.instruction) >= 1

    @given(pair=instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_context_is_non_empty(self, pair: InstructionTuningPair) -> None:
        """Context field must be a non-empty string."""
        assert isinstance(pair.context, str)
        assert len(pair.context) >= 1

    @given(pair=instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_response_is_non_empty(self, pair: InstructionTuningPair) -> None:
        """Response field must be a non-empty string."""
        assert isinstance(pair.response, str)
        assert len(pair.response) >= 1

    @given(pair=instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_strategy_is_valid(self, pair: InstructionTuningPair) -> None:
        """Metadata strategy must be one of the valid strategy names."""
        assert pair.metadata.strategy in VALID_STRATEGIES

    @given(pair=instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_confidence_score_in_range(self, pair: InstructionTuningPair) -> None:
        """Metadata confidence_score must be in [0.0, 1.0]."""
        assert 0.0 <= pair.metadata.confidence_score <= 1.0

    @given(pair=instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_all_structural_invariants_hold(self, pair: InstructionTuningPair) -> None:
        """Combined check: all structural invariants hold simultaneously."""
        # Non-empty text fields
        assert len(pair.instruction) >= 1
        assert len(pair.context) >= 1
        assert len(pair.response) >= 1

        # Valid metadata
        assert pair.metadata.strategy in VALID_STRATEGIES
        assert 0.0 <= pair.metadata.confidence_score <= 1.0

        # Metadata is a PairMetadata instance
        assert isinstance(pair.metadata, PairMetadata)

        # source_concepts is a list
        assert isinstance(pair.metadata.source_concepts, list)


# ---------------------------------------------------------------------------
# Negative tests: Pydantic rejects invalid inputs
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestInstructionTuningPairRejectsInvalid:
    """Verify that the Pydantic model rejects structurally invalid inputs."""

    @given(
        strategy=st.text(min_size=1, max_size=50).filter(
            lambda s: s not in VALID_STRATEGIES
        )
    )
    @settings(max_examples=100)
    def test_rejects_invalid_strategy(self, strategy: str) -> None:
        """An invalid strategy value must raise a ValidationError."""
        with pytest.raises(Exception):
            PairMetadata(
                strategy=strategy,
                confidence_score=0.5,
            )

    @given(
        score=st.one_of(
            st.floats(max_value=-0.01, allow_nan=False, allow_infinity=False),
            st.floats(min_value=1.01, allow_nan=False, allow_infinity=False),
        )
    )
    @settings(max_examples=100)
    def test_rejects_out_of_range_confidence(self, score: float) -> None:
        """A confidence_score outside [0.0, 1.0] must raise a ValidationError."""
        with pytest.raises(Exception):
            PairMetadata(
                strategy="kg",
                confidence_score=score,
            )

    def test_rejects_empty_instruction(self) -> None:
        """An empty instruction string must raise a ValidationError."""
        with pytest.raises(Exception):
            InstructionTuningPair(
                instruction="",
                context="some context",
                response="some response",
                metadata=PairMetadata(
                    strategy="kg",
                    confidence_score=0.5,
                ),
            )

    def test_rejects_empty_context(self) -> None:
        """An empty context string must raise a ValidationError."""
        with pytest.raises(Exception):
            InstructionTuningPair(
                instruction="some question",
                context="",
                response="some response",
                metadata=PairMetadata(
                    strategy="rag",
                    confidence_score=0.8,
                ),
            )

    def test_rejects_empty_response(self) -> None:
        """An empty response string must raise a ValidationError."""
        with pytest.raises(Exception):
            InstructionTuningPair(
                instruction="some question",
                context="some context",
                response="",
                metadata=PairMetadata(
                    strategy="umls_reasoning",
                    confidence_score=0.9,
                ),
            )


# ---------------------------------------------------------------------------
# Property 18: JSONL round-trip serialization
# ---------------------------------------------------------------------------


def _unicode_text() -> st.SearchStrategy[str]:
    """Generate non-empty strings with arbitrary Unicode content.

    Includes characters from the full Unicode BMP: Latin, CJK, Cyrillic,
    Arabic, emoji, mathematical symbols, etc. Filters out strings that are
    only whitespace (which would fail the min_length=1 Pydantic validator
    for stripped content).
    """
    return st.text(
        alphabet=st.characters(
            codec="utf-8",
            categories=(
                "L",   # Letters (Latin, CJK, Cyrillic, Arabic, etc.)
                "N",   # Numbers
                "P",   # Punctuation
                "S",   # Symbols (emoji, math, currency)
                "Z",   # Separators (spaces)
            ),
            exclude_characters="\x00",  # Exclude null bytes (invalid in JSON)
        ),
        min_size=1,
        max_size=300,
    ).filter(lambda s: s.strip())


def _unicode_optional_text() -> st.SearchStrategy[Optional[str]]:
    """Generate either None or a non-empty Unicode string."""
    return st.one_of(st.none(), _unicode_text())


def unicode_pair_metadata_strategy() -> st.SearchStrategy[PairMetadata]:
    """Generate a valid PairMetadata with arbitrary Unicode in text fields."""
    return st.builds(
        PairMetadata,
        strategy=_strategy_name(),
        source_concepts=st.lists(_unicode_text(), max_size=5),
        confidence_score=_confidence_score(),
        source_document=_unicode_optional_text(),
        chunk_ids=st.one_of(
            st.none(),
            st.lists(_unicode_text(), max_size=5),
        ),
        relationship_chain=_unicode_optional_text(),
    )


def unicode_instruction_tuning_pair_strategy() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a valid InstructionTuningPair with arbitrary Unicode content."""
    return st.builds(
        InstructionTuningPair,
        instruction=_unicode_text(),
        context=_unicode_text(),
        response=_unicode_text(),
        metadata=unicode_pair_metadata_strategy(),
    )


@pytest.mark.pbt
@pytest.mark.unit
class TestJSONLRoundTripSerialization:
    """Property 18: JSONL round-trip serialization.

    # Feature: medical-knowledge-finetuning, Property 18: JSONL round-trip serialization

    For any valid InstructionTuningPair (including arbitrary Unicode content),
    serializing it to a JSONL line and then parsing that line back SHALL
    produce an InstructionTuningPair that is equivalent to the original
    (all fields match, including metadata).

    Validates: Requirements 12.1, 12.2, 12.3
    """

    @given(pair=unicode_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_equality(self, pair: InstructionTuningPair) -> None:
        """parse(print(x)) == x for any valid InstructionTuningPair."""
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored == pair

    @given(pair=unicode_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_instruction(self, pair: InstructionTuningPair) -> None:
        """Instruction text survives serialization round-trip exactly."""
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored.instruction == pair.instruction

    @given(pair=unicode_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_context(self, pair: InstructionTuningPair) -> None:
        """Context text survives serialization round-trip exactly."""
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored.context == pair.context

    @given(pair=unicode_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_response(self, pair: InstructionTuningPair) -> None:
        """Response text survives serialization round-trip exactly."""
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored.response == pair.response

    @given(pair=unicode_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_round_trip_preserves_metadata(self, pair: InstructionTuningPair) -> None:
        """All metadata fields survive serialization round-trip exactly."""
        jsonl_line = pair.to_jsonl_line()
        restored = InstructionTuningPair.from_jsonl_line(jsonl_line)
        assert restored.metadata.strategy == pair.metadata.strategy
        assert restored.metadata.confidence_score == pair.metadata.confidence_score
        assert restored.metadata.source_concepts == pair.metadata.source_concepts
        assert restored.metadata.source_document == pair.metadata.source_document
        assert restored.metadata.chunk_ids == pair.metadata.chunk_ids
        assert restored.metadata.relationship_chain == pair.metadata.relationship_chain

    @given(pair=unicode_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_serialized_line_is_valid_json(self, pair: InstructionTuningPair) -> None:
        """The serialized JSONL line is valid JSON with expected top-level keys."""
        jsonl_line = pair.to_jsonl_line()
        parsed = json.loads(jsonl_line)
        assert isinstance(parsed, dict)
        assert set(parsed.keys()) == {"instruction", "context", "response", "metadata"}

    @given(pair=unicode_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_serialized_line_is_single_line(self, pair: InstructionTuningPair) -> None:
        """The serialized output is a single line (no embedded newlines in JSON)."""
        jsonl_line = pair.to_jsonl_line()
        assert "\n" not in jsonl_line

    @given(pair=unicode_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_double_round_trip(self, pair: InstructionTuningPair) -> None:
        """Two consecutive round-trips produce the same result (idempotence)."""
        line1 = pair.to_jsonl_line()
        restored1 = InstructionTuningPair.from_jsonl_line(line1)
        line2 = restored1.to_jsonl_line()
        restored2 = InstructionTuningPair.from_jsonl_line(line2)
        assert restored2 == pair
        assert line1 == line2


# ---------------------------------------------------------------------------
# Property 19: Graceful handling of invalid JSONL lines
# ---------------------------------------------------------------------------


def _invalid_jsonl_line() -> st.SearchStrategy[str]:
    """Generate strings that are NOT valid InstructionTuningPair JSON.

    Produces several categories of invalid lines:
    - Malformed JSON (not parseable)
    - Valid JSON but wrong type (array, string, number)
    - Valid JSON object but missing required fields
    - Valid JSON object with empty required fields
    - Valid JSON object with invalid metadata values
    """
    malformed_json = st.sampled_from([
        "{bad json",
        "not json at all",
        '{"instruction": "q", "context": "c", response: "r"}',
        "{",
        "",
        "null",
        "undefined",
        '{"instruction": "q", "context": "c",}',
    ])

    wrong_json_type = st.sampled_from([
        "[]",
        '"just a string"',
        "42",
        "true",
        "false",
        "[1, 2, 3]",
    ])

    missing_required_fields = st.sampled_from([
        json.dumps({"instruction": "q"}),
        json.dumps({"instruction": "q", "context": "c"}),
        json.dumps({"context": "c", "response": "r"}),
        json.dumps({
            "instruction": "q",
            "context": "c",
            "response": "r",
        }),  # missing metadata
        json.dumps({
            "instruction": "q",
            "context": "c",
            "response": "r",
            "metadata": {},
        }),  # metadata missing required fields
    ])

    invalid_field_values = st.sampled_from([
        json.dumps({
            "instruction": "",
            "context": "c",
            "response": "r",
            "metadata": {
                "strategy": "kg",
                "confidence_score": 0.5,
            },
        }),  # empty instruction
        json.dumps({
            "instruction": "q",
            "context": "",
            "response": "r",
            "metadata": {
                "strategy": "kg",
                "confidence_score": 0.5,
            },
        }),  # empty context
        json.dumps({
            "instruction": "q",
            "context": "c",
            "response": "r",
            "metadata": {
                "strategy": "invalid_strategy",
                "confidence_score": 0.5,
            },
        }),  # invalid strategy
        json.dumps({
            "instruction": "q",
            "context": "c",
            "response": "r",
            "metadata": {
                "strategy": "kg",
                "confidence_score": 2.0,
            },
        }),  # confidence out of range
    ])

    return st.one_of(
        malformed_json,
        wrong_json_type,
        missing_required_fields,
        invalid_field_values,
    )


def parse_jsonl_lines(
    lines: List[str],
    logger: logging.Logger,
) -> Tuple[List[InstructionTuningPair], List[int]]:
    """Parse a list of JSONL lines, skipping invalid ones.

    This is the reference implementation for the contract specified
    in Requirement 12.4 and Property 19. The actual
    ``TrainingDataGenerator.parse_jsonl()`` (task 6.1) must match
    this behaviour.

    Returns
    -------
    parsed : list[InstructionTuningPair]
        Successfully parsed pairs, in order of appearance.
    skipped_line_numbers : list[int]
        1-based line numbers of lines that were skipped.
    """
    parsed: List[InstructionTuningPair] = []
    skipped: List[int] = []

    for line_number, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            skipped.append(line_number)
            logger.warning(
                "Skipping invalid JSONL line %d: empty line",
                line_number,
            )
            continue
        try:
            pair = InstructionTuningPair.from_jsonl_line(stripped)
            parsed.append(pair)
        except Exception as exc:
            skipped.append(line_number)
            logger.warning(
                "Skipping invalid JSONL line %d: %s",
                line_number,
                exc,
            )

    return parsed, skipped


@pytest.mark.pbt
@pytest.mark.unit
class TestGracefulHandlingOfInvalidJSONLLines:
    """Property 19: Graceful handling of invalid JSONL lines.

    # Feature: medical-knowledge-finetuning, Property 19: Graceful handling of invalid JSONL lines

    For any JSONL file containing a mix of valid and invalid lines,
    parsing SHALL return InstructionTuningPair objects for all valid
    lines and skip all invalid lines, with each skipped line producing
    a log entry containing the line number.

    Validates: Requirements 12.4
    """

    # ------------------------------------------------------------------
    # Hypothesis strategy: interleaved valid + invalid lines
    # ------------------------------------------------------------------

    @staticmethod
    def _mixed_lines_strategy():
        """Generate a list of (line_text, is_valid, original_pair) tuples.

        Each element is either:
        - A valid JSONL line (serialized from a generated pair)
        - An invalid JSONL line (from the invalid generator)
        """
        valid_entry = (
            unicode_instruction_tuning_pair_strategy()
            .map(lambda p: (p.to_jsonl_line(), True, p))
        )
        invalid_entry = (
            _invalid_jsonl_line()
            .map(lambda line: (line, False, None))
        )
        return st.lists(
            st.one_of(valid_entry, invalid_entry),
            min_size=1,
            max_size=30,
        )

    # ------------------------------------------------------------------
    # Core property: valid lines parsed, invalid lines skipped
    # ------------------------------------------------------------------

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_valid_lines_are_parsed_invalid_are_skipped(
        self,
        data,
    ) -> None:
        """All valid lines produce correct pairs; invalid are skipped."""
        entries = data.draw(self._mixed_lines_strategy())
        lines = [entry[0] for entry in entries]

        logger = logging.getLogger("test_property19")
        parsed, skipped = parse_jsonl_lines(lines, logger)

        expected_valid = [
            (i + 1, entry[2])
            for i, entry in enumerate(entries)
            if entry[1]
        ]
        expected_invalid_line_nums = [
            i + 1
            for i, entry in enumerate(entries)
            if not entry[1]
        ]

        # Every valid line should produce a parsed pair
        assert len(parsed) == len(expected_valid), (
            f"Expected {len(expected_valid)} parsed pairs, "
            f"got {len(parsed)}"
        )

        # Parsed pairs match originals in order
        for (_, original), restored in zip(
            expected_valid, parsed
        ):
            assert restored == original

        # Every invalid line number appears in skipped
        assert sorted(skipped) == sorted(
            expected_invalid_line_nums
        )

    # ------------------------------------------------------------------
    # Property: skipped line numbers are logged
    # ------------------------------------------------------------------

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_skipped_lines_are_logged_with_line_numbers(
        self,
        data,
    ) -> None:
        """Each skipped line produces a log entry with its line number."""
        entries = data.draw(self._mixed_lines_strategy())
        lines = [entry[0] for entry in entries]

        logger = logging.getLogger("test_property19_log")
        handler = logging.handlers.MemoryHandler(
            capacity=10000,
            flushLevel=logging.CRITICAL + 1,
        )
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            _, skipped = parse_jsonl_lines(lines, logger)

            # Each skipped line number must appear in a log record
            for line_num in skipped:
                assert any(
                    str(line_num) in record.getMessage()
                    for record in handler.buffer
                ), (
                    f"Line number {line_num} not found "
                    f"in log records"
                )
        finally:
            logger.removeHandler(handler)
            handler.close()

    # ------------------------------------------------------------------
    # Property: all-valid file produces no skips
    # ------------------------------------------------------------------

    @given(
        pairs=st.lists(
            unicode_instruction_tuning_pair_strategy(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_all_valid_lines_produce_no_skips(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """A file with only valid lines has zero skipped lines."""
        lines = [p.to_jsonl_line() for p in pairs]
        logger = logging.getLogger("test_property19_valid")
        parsed, skipped = parse_jsonl_lines(lines, logger)

        assert len(parsed) == len(pairs)
        assert skipped == []
        for original, restored in zip(pairs, parsed):
            assert restored == original

    # ------------------------------------------------------------------
    # Property: all-invalid file produces no parsed pairs
    # ------------------------------------------------------------------

    @given(
        invalid_lines=st.lists(
            _invalid_jsonl_line(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(max_examples=100)
    def test_all_invalid_lines_produce_no_parsed_pairs(
        self,
        invalid_lines: List[str],
    ) -> None:
        """A file with only invalid lines produces zero parsed pairs."""
        logger = logging.getLogger("test_property19_invalid")
        parsed, skipped = parse_jsonl_lines(
            invalid_lines, logger
        )

        assert len(parsed) == 0
        assert len(skipped) == len(invalid_lines)

    # ------------------------------------------------------------------
    # Property: parse from file on disk matches in-memory parse
    # ------------------------------------------------------------------

    @given(
        data=st.data(),
    )
    @settings(max_examples=50)
    def test_file_based_parsing_matches_in_memory(
        self,
        data,
    ) -> None:
        """Writing lines to a temp file and reading back gives same result."""
        entries = data.draw(self._mixed_lines_strategy())
        lines = [entry[0] for entry in entries]

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".jsonl",
            encoding="utf-8",
            delete=False,
        ) as f:
            for line in lines:
                f.write(line + "\n")
            tmp_path = Path(f.name)

        try:
            # Parse from file
            file_lines = tmp_path.read_text(
                encoding="utf-8"
            ).splitlines()
            logger = logging.getLogger("test_property19_file")
            parsed_file, skipped_file = parse_jsonl_lines(
                file_lines, logger
            )

            # Parse from memory
            logger2 = logging.getLogger("test_property19_mem")
            parsed_mem, skipped_mem = parse_jsonl_lines(
                lines, logger2
            )

            assert len(parsed_file) == len(parsed_mem)
            assert skipped_file == skipped_mem
            for pf, pm in zip(parsed_file, parsed_mem):
                assert pf == pm
        finally:
            tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # Property: line count invariant
    # ------------------------------------------------------------------

    @given(
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_parsed_plus_skipped_equals_total_lines(
        self,
        data,
    ) -> None:
        """parsed count + skipped count == total line count."""
        entries = data.draw(self._mixed_lines_strategy())
        lines = [entry[0] for entry in entries]

        logger = logging.getLogger("test_property19_count")
        parsed, skipped = parse_jsonl_lines(lines, logger)

        assert len(parsed) + len(skipped) == len(lines)
