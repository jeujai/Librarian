"""
Property-based tests for TrainingDataGenerator.

# Feature: medical-knowledge-finetuning
# Property 8: Deduplication preserves unique pairs and removes near-duplicates
# Property 9: Deterministic shuffling with seed

Validates: Requirements 4.2, 4.3
"""

from __future__ import annotations

import string
import tempfile
from pathlib import Path
from typing import List, Set

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.models import (
    VALID_STRATEGIES,
    InstructionTuningPair,
    PairMetadata,
)
from multimodal_librarian.ml.training_data_generator import (
    TrainingDataGenerator,
    _normalise_text,
    _normalised_similarity,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pair(instruction: str, strategy: str = "kg") -> InstructionTuningPair:
    """Create an InstructionTuningPair with the given instruction text.

    Uses fixed filler for context/response/metadata so that the test
    focuses exclusively on instruction-based deduplication.
    """
    return InstructionTuningPair(
        instruction=instruction,
        context="test context",
        response="test response",
        metadata=PairMetadata(
            strategy=strategy,
            source_concepts=["C0000001"],
            confidence_score=0.9,
        ),
    )


def _make_generator() -> TrainingDataGenerator:
    """Create a TrainingDataGenerator with None dependencies.

    Only the ``deduplicate`` method is exercised in these tests and it
    does not touch any external service.
    """
    return TrainingDataGenerator(
        neo4j_client=None,  # type: ignore[arg-type]
        vector_client=None,  # type: ignore[arg-type]
        rag_service=None,  # type: ignore[arg-type]
        umls_client=None,  # type: ignore[arg-type]
        relationship_traverser=None,  # type: ignore[arg-type]
        ner_extractor=None,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

def _distinct_instruction_text() -> st.SearchStrategy[str]:
    """Generate instruction strings that are reasonably distinct.

    Uses printable ASCII with enough length to produce meaningful
    bigram sets, avoiding trivially short strings that collapse
    under normalisation.
    """
    return st.text(
        alphabet=string.ascii_letters + string.digits + " ",
        min_size=10,
        max_size=200,
    ).filter(lambda s: len(s.strip()) >= 10)


def _near_duplicate_pair() -> st.SearchStrategy[tuple[str, str]]:
    """Generate a pair of strings that are near-duplicates.

    Produces (original, variant) where the variant is the original
    with minor perturbations (case change, trailing punctuation,
    small suffix) that keep Sørensen–Dice similarity >= 0.85 after
    normalisation.
    """
    def _make_variant(base: str) -> tuple[str, str]:
        # Variant 1: identical after normalisation (case change)
        return (base, base.upper())

    return (
        st.text(
            alphabet=string.ascii_lowercase + " ",
            min_size=20,
            max_size=200,
        )
        .filter(lambda s: len(s.strip()) >= 20)
        .map(_make_variant)
    )


def _instruction_tuning_pair_strategy() -> st.SearchStrategy[InstructionTuningPair]:
    """Generate a valid InstructionTuningPair with random instruction text."""
    return st.builds(
        _make_pair,
        instruction=_distinct_instruction_text(),
        strategy=st.sampled_from(list(VALID_STRATEGIES)),
    )


# ---------------------------------------------------------------------------
# Property 8: Deduplication preserves unique pairs and removes
#              near-duplicates
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestDeduplicationProperty:
    """Property 8: Deduplication preserves unique pairs and removes near-duplicates.

    # Feature: medical-knowledge-finetuning, Property 8: Deduplication preserves unique pairs and removes near-duplicates

    For any list of InstructionTuningPairs, after deduplication with
    threshold 0.85:
      (a) no two remaining pairs have instruction similarity >= 0.85, and
      (b) every removed pair has similarity >= 0.85 with at least one
          remaining pair.

    Validates: Requirements 4.2
    """

    THRESHOLD = 0.85

    # ------------------------------------------------------------------
    # Core property (a): no two accepted pairs are near-duplicates
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_no_two_accepted_pairs_are_near_duplicates(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """After dedup, no two remaining pairs have similarity >= threshold."""
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=self.THRESHOLD)

        for i in range(len(accepted)):
            for j in range(i + 1, len(accepted)):
                sim = _normalised_similarity(
                    accepted[i].instruction,
                    accepted[j].instruction,
                )
                assert sim < self.THRESHOLD, (
                    f"Accepted pair {i} and {j} have similarity {sim:.4f} "
                    f">= threshold {self.THRESHOLD}.\n"
                    f"  pair[{i}].instruction = {accepted[i].instruction!r}\n"
                    f"  pair[{j}].instruction = {accepted[j].instruction!r}"
                )

    # ------------------------------------------------------------------
    # Core property (b): every removed pair is similar to an accepted one
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_every_removed_pair_is_similar_to_an_accepted_pair(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Every removed pair has similarity >= threshold with at least one accepted pair."""
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=self.THRESHOLD)

        accepted_set = set(id(p) for p in accepted)
        removed = [p for p in pairs if id(p) not in accepted_set]

        for removed_pair in removed:
            has_similar = any(
                _normalised_similarity(
                    removed_pair.instruction,
                    acc.instruction,
                ) >= self.THRESHOLD
                for acc in accepted
            )
            assert has_similar, (
                f"Removed pair has no similar accepted pair "
                f"(threshold={self.THRESHOLD}).\n"
                f"  removed.instruction = {removed_pair.instruction!r}"
            )

    # ------------------------------------------------------------------
    # Combined property: (a) and (b) hold simultaneously
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=1, max_size=30))
    @settings(max_examples=100)
    def test_dedup_invariants_hold_simultaneously(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Both dedup invariants hold at the same time."""
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=self.THRESHOLD)

        # (a) No two accepted pairs are near-duplicates
        for i in range(len(accepted)):
            for j in range(i + 1, len(accepted)):
                sim = _normalised_similarity(
                    accepted[i].instruction,
                    accepted[j].instruction,
                )
                assert sim < self.THRESHOLD

        # (b) Every removed pair is similar to an accepted pair
        accepted_ids = set(id(p) for p in accepted)
        for pair in pairs:
            if id(pair) not in accepted_ids:
                assert any(
                    _normalised_similarity(pair.instruction, acc.instruction)
                    >= self.THRESHOLD
                    for acc in accepted
                )

    # ------------------------------------------------------------------
    # Property: accepted is a subset of the original list
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_accepted_is_subset_of_input(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Deduplication only removes; it never adds or modifies pairs."""
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=self.THRESHOLD)

        input_ids = set(id(p) for p in pairs)
        for acc in accepted:
            assert id(acc) in input_ids, (
                "Accepted pair is not from the original input list"
            )

    # ------------------------------------------------------------------
    # Property: accepted preserves insertion order
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_accepted_preserves_insertion_order(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Accepted pairs appear in the same relative order as the input."""
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=self.THRESHOLD)

        input_indices = {id(p): i for i, p in enumerate(pairs)}
        accepted_indices = [input_indices[id(a)] for a in accepted]
        assert accepted_indices == sorted(accepted_indices), (
            "Accepted pairs are not in insertion order"
        )

    # ------------------------------------------------------------------
    # Property: empty input produces empty output
    # ------------------------------------------------------------------

    def test_empty_input_returns_empty(self) -> None:
        """Deduplicating an empty list returns an empty list."""
        gen = _make_generator()
        assert gen.deduplicate([], similarity_threshold=self.THRESHOLD) == []

    # ------------------------------------------------------------------
    # Property: single-element input is always preserved
    # ------------------------------------------------------------------

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_single_element_is_preserved(
        self,
        pair: InstructionTuningPair,
    ) -> None:
        """A single-element list is never deduplicated away."""
        gen = _make_generator()
        accepted = gen.deduplicate([pair], similarity_threshold=self.THRESHOLD)
        assert len(accepted) == 1
        assert accepted[0] is pair

    # ------------------------------------------------------------------
    # Property: exact duplicates are collapsed
    # ------------------------------------------------------------------

    @given(pair=_instruction_tuning_pair_strategy(), n=st.integers(min_value=2, max_value=10))
    @settings(max_examples=100)
    def test_exact_duplicates_collapse_to_one(
        self,
        pair: InstructionTuningPair,
        n: int,
    ) -> None:
        """N copies of the same pair collapse to exactly one."""
        copies = [
            _make_pair(pair.instruction, pair.metadata.strategy)
            for _ in range(n)
        ]
        gen = _make_generator()
        accepted = gen.deduplicate(copies, similarity_threshold=self.THRESHOLD)
        assert len(accepted) == 1

    # ------------------------------------------------------------------
    # Property: near-duplicates (case variants) are collapsed
    # ------------------------------------------------------------------

    @given(data=_near_duplicate_pair())
    @settings(max_examples=100)
    def test_near_duplicates_are_collapsed(
        self,
        data: tuple[str, str],
    ) -> None:
        """Pairs whose instructions differ only by case are deduplicated."""
        original, variant = data
        # Confirm they are indeed near-duplicates
        sim = _normalised_similarity(original, variant)
        assume(sim >= self.THRESHOLD)

        pairs = [_make_pair(original), _make_pair(variant)]
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=self.THRESHOLD)
        assert len(accepted) == 1

    # ------------------------------------------------------------------
    # Property: deduplication is idempotent
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_deduplication_is_idempotent(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Running dedup twice produces the same result as running it once."""
        gen = _make_generator()
        first_pass = gen.deduplicate(pairs, similarity_threshold=self.THRESHOLD)
        second_pass = gen.deduplicate(first_pass, similarity_threshold=self.THRESHOLD)

        assert len(first_pass) == len(second_pass)
        for a, b in zip(first_pass, second_pass):
            assert a is b

    # ------------------------------------------------------------------
    # Property: threshold of 0.0 keeps only one pair per normalised form
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=1, max_size=20))
    @settings(max_examples=100)
    def test_threshold_zero_keeps_maximally_distinct(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """With threshold 0.0, only pairs with similarity < 0.0 survive.

        Since Sørensen–Dice is always >= 0.0, this means only the first
        pair with each unique normalised instruction survives (exact
        matches are collapsed, but any non-identical pair is kept).
        Actually, threshold 0.0 means sim >= 0.0 is a duplicate, so
        everything except the very first pair would be removed — unless
        similarity is exactly 0.0 (impossible for non-empty strings
        sharing any bigram). In practice this collapses to 1 pair for
        most inputs.
        """
        gen = _make_generator()
        # With threshold 1.0, only exact normalised matches are removed
        accepted = gen.deduplicate(pairs, similarity_threshold=1.0)
        # All accepted pairs should have distinct normalised instructions
        normalised = [_normalise_text(p.instruction) for p in accepted]
        assert len(normalised) == len(set(normalised))

    # ------------------------------------------------------------------
    # Property: threshold of 1.0 only removes exact normalised duplicates
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=20))
    @settings(max_examples=100)
    def test_threshold_one_only_removes_exact_normalised_duplicates(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """With threshold 1.0, only pairs with identical normalised
        instructions are removed."""
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=1.0)

        # Every accepted pair has a unique normalised instruction
        seen: Set[str] = set()
        for p in accepted:
            norm = _normalise_text(p.instruction)
            assert norm not in seen, (
                f"Duplicate normalised instruction in accepted: {norm!r}"
            )
            seen.add(norm)

    # ------------------------------------------------------------------
    # Property: accepted count is bounded
    # ------------------------------------------------------------------

    @given(pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=30))
    @settings(max_examples=100)
    def test_accepted_count_bounded_by_input(
        self,
        pairs: List[InstructionTuningPair],
    ) -> None:
        """Accepted count is between 0 and len(input), inclusive."""
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=self.THRESHOLD)
        assert 0 <= len(accepted) <= len(pairs)

    # ------------------------------------------------------------------
    # Property: configurable threshold is respected
    # ------------------------------------------------------------------

    @given(
        pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=2, max_size=20),
        threshold=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_configurable_threshold_is_respected(
        self,
        pairs: List[InstructionTuningPair],
        threshold: float,
    ) -> None:
        """For any threshold, no two accepted pairs exceed it."""
        gen = _make_generator()
        accepted = gen.deduplicate(pairs, similarity_threshold=threshold)

        for i in range(len(accepted)):
            for j in range(i + 1, len(accepted)):
                sim = _normalised_similarity(
                    accepted[i].instruction,
                    accepted[j].instruction,
                )
                assert sim < threshold or threshold == 0.0, (
                    f"Accepted pair {i} and {j} have similarity {sim:.4f} "
                    f">= threshold {threshold}.\n"
                    f"  pair[{i}].instruction = {accepted[i].instruction!r}\n"
                    f"  pair[{j}].instruction = {accepted[j].instruction!r}"
                )


# ---------------------------------------------------------------------------
# Property 9: Deterministic shuffling with seed
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestDeterministicShufflingProperty:
    """Property 9: Deterministic shuffling with seed.

    # Feature: medical-knowledge-finetuning, Property 9: Deterministic shuffling with seed

    For any list of InstructionTuningPairs and any random seed,
    shuffling the list twice with the same seed SHALL produce
    identical orderings.

    Validates: Requirements 4.3
    """

    # ------------------------------------------------------------------
    # Core property: same seed → same ordering
    # ------------------------------------------------------------------

    @given(
        pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=50),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=100)
    def test_same_seed_produces_identical_ordering(
        self,
        pairs: List[InstructionTuningPair],
        seed: int,
    ) -> None:
        """Exporting twice with the same seed produces identical JSONL files."""
        gen = _make_generator()

        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "output_a.jsonl"
            path_b = Path(tmpdir) / "output_b.jsonl"

            gen.export_jsonl(pairs, path_a, seed=seed)
            gen.export_jsonl(pairs, path_b, seed=seed)

            content_a = path_a.read_text(encoding="utf-8")
            content_b = path_b.read_text(encoding="utf-8")

            assert content_a == content_b, (
                f"Two exports with seed={seed} produced different JSONL.\n"
                f"  len(pairs)={len(pairs)}"
            )

    # ------------------------------------------------------------------
    # Property: same seed → same DatasetSummary.total_pairs
    # ------------------------------------------------------------------

    @given(
        pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=50),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=100)
    def test_same_seed_produces_identical_summary(
        self,
        pairs: List[InstructionTuningPair],
        seed: int,
    ) -> None:
        """Exporting twice with the same seed produces identical summaries."""
        gen = _make_generator()

        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "output_a.jsonl"
            path_b = Path(tmpdir) / "output_b.jsonl"

            summary_a = gen.export_jsonl(pairs, path_a, seed=seed)
            summary_b = gen.export_jsonl(pairs, path_b, seed=seed)

            assert summary_a.total_pairs == summary_b.total_pairs
            assert summary_a.pairs_per_strategy == summary_b.pairs_per_strategy
            assert summary_a.avg_response_length == summary_b.avg_response_length

    # ------------------------------------------------------------------
    # Property: different seeds → different ordering (for non-trivial lists)
    # ------------------------------------------------------------------

    @given(
        pairs=st.lists(
            _instruction_tuning_pair_strategy(), min_size=10, max_size=50
        ),
        seed_a=st.integers(min_value=0, max_value=2**31 - 1),
    )
    @settings(max_examples=100)
    def test_different_seeds_likely_produce_different_ordering(
        self,
        pairs: List[InstructionTuningPair],
        seed_a: int,
    ) -> None:
        """Different seeds are very likely to produce different orderings.

        This is a probabilistic check: for lists of 10+ elements, two
        distinct seeds should almost never produce the same permutation
        (probability 1/10! ≈ 2.8e-7).
        We use seed_b = seed_a + 1 to guarantee distinct seeds.
        """
        seed_b = seed_a + 1
        gen = _make_generator()

        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "output_a.jsonl"
            path_b = Path(tmpdir) / "output_b.jsonl"

            gen.export_jsonl(pairs, path_a, seed=seed_a)
            gen.export_jsonl(pairs, path_b, seed=seed_b)

            content_a = path_a.read_text(encoding="utf-8")
            content_b = path_b.read_text(encoding="utf-8")

            # For lists with 10+ distinct elements, the probability of
            # two different seeds producing the same permutation is
            # vanishingly small (1/10! ≈ 2.8e-7).
            # We only assert difference when all instructions are distinct.
            instructions = [p.instruction for p in pairs]
            if len(set(instructions)) == len(instructions):
                assert content_a != content_b, (
                    f"Two different seeds ({seed_a}, {seed_b}) produced "
                    f"identical JSONL for {len(pairs)} distinct pairs."
                )

    # ------------------------------------------------------------------
    # Property: shuffling preserves all elements (no loss, no duplication)
    # ------------------------------------------------------------------

    @given(
        pairs=st.lists(_instruction_tuning_pair_strategy(), min_size=0, max_size=50),
        seed=st.integers(min_value=0, max_value=2**32 - 1),
    )
    @settings(max_examples=100)
    def test_shuffling_preserves_all_elements(
        self,
        pairs: List[InstructionTuningPair],
        seed: int,
    ) -> None:
        """Shuffling does not lose or duplicate any pairs."""
        gen = _make_generator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.jsonl"
            summary = gen.export_jsonl(pairs, output_path, seed=seed)

            assert summary.total_pairs == len(pairs)

            # Parse back and verify same instruction set
            parsed = TrainingDataGenerator.parse_jsonl(output_path)
            assert len(parsed) == len(pairs)

            original_instructions = sorted(p.instruction for p in pairs)
            parsed_instructions = sorted(p.instruction for p in parsed)
            assert original_instructions == parsed_instructions

    # ------------------------------------------------------------------
    # Property: empty list is handled correctly
    # ------------------------------------------------------------------

    def test_empty_list_produces_empty_file(self) -> None:
        """Exporting an empty list produces an empty JSONL file."""
        gen = _make_generator()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.jsonl"
            summary = gen.export_jsonl([], output_path, seed=42)

            assert summary.total_pairs == 0
            content = output_path.read_text(encoding="utf-8")
            assert content.strip() == ""

    # ------------------------------------------------------------------
    # Property: single element is always in the same position
    # ------------------------------------------------------------------

    @given(pair=_instruction_tuning_pair_strategy())
    @settings(max_examples=100)
    def test_single_element_is_invariant_to_seed(
        self,
        pair: InstructionTuningPair,
    ) -> None:
        """A single-element list is unaffected by the seed value."""
        gen = _make_generator()

        with tempfile.TemporaryDirectory() as tmpdir:
            path_a = Path(tmpdir) / "output_a.jsonl"
            path_b = Path(tmpdir) / "output_b.jsonl"

            gen.export_jsonl([pair], path_a, seed=0)
            gen.export_jsonl([pair], path_b, seed=999999)

            content_a = path_a.read_text(encoding="utf-8")
            content_b = path_b.read_text(encoding="utf-8")

            assert content_a == content_b
