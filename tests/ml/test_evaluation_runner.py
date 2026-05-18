"""
Property-based tests for EvaluationRunner.

# Feature: medical-knowledge-finetuning
# Property 12: Evaluation set excludes training questions
# Property 13: Evaluation set JSONL format

Validates: Requirements 7.2, 7.5
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from unittest.mock import AsyncMock

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from multimodal_librarian.ml.evaluation_runner import (
    _EVAL_TEMPLATES,
    EVAL_SEMANTIC_TYPES,
    EvaluationRunner,
)
from multimodal_librarian.ml.models import (
    VALID_DIFFICULTY_LEVELS,
    ComparisonReport,
    EvaluationConfig,
    EvaluationQuestion,
    EvaluationSet,
    QuestionResult,
    ResponseScore,
)

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------


def _concept_name() -> st.SearchStrategy[str]:
    """Generate plausible concept names (non-empty, printable)."""
    return st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
        min_size=2,
        max_size=60,
    ).filter(lambda s: s.strip())


def _semantic_type() -> st.SearchStrategy[str]:
    """Pick a semantic type that has templates defined."""
    types_with_templates = [t for t in EVAL_SEMANTIC_TYPES if t in _EVAL_TEMPLATES]
    return st.sampled_from(types_with_templates)


def _training_question_set(
    semantic_types: Optional[List[str]] = None,
) -> st.SearchStrategy[Set[str]]:
    """Generate a set of training question strings.

    Questions are built from the same templates used by the evaluation
    runner so that overlap is realistic.
    """
    if semantic_types is None:
        semantic_types = [t for t in EVAL_SEMANTIC_TYPES if t in _EVAL_TEMPLATES]

    def _make_question(data):
        sem_type = data.draw(st.sampled_from(semantic_types))
        templates = _EVAL_TEMPLATES[sem_type]
        template = data.draw(st.sampled_from(templates))
        concept = data.draw(_concept_name())
        return template.format(concept_name=concept)

    return st.data().flatmap(
        lambda _: st.sets(
            st.builds(
                lambda sem, concept: _EVAL_TEMPLATES[sem][0].format(concept_name=concept),
                sem=st.sampled_from(semantic_types),
                concept=_concept_name(),
            ),
            min_size=0,
            max_size=30,
        )
    )


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------


def _make_mock_neo4j(concepts_by_type: Dict[str, List[str]]) -> AsyncMock:
    """Create a mock Neo4j client that returns concepts per semantic type.

    Parameters
    ----------
    concepts_by_type:
        Mapping from semantic type to list of preferred_name strings.
    """
    mock = AsyncMock()

    async def _execute_query(query: str, params: Dict[str, Any]) -> List[Dict[str, str]]:
        sem_type = params.get("semantic_type", "")
        limit = params.get("limit", 10)
        names = concepts_by_type.get(sem_type, [])
        return [
            {"preferred_name": name, "cui": f"C{i:07d}"}
            for i, name in enumerate(names[:limit])
        ]

    mock.execute_query = AsyncMock(side_effect=_execute_query)
    return mock


def _make_mock_rag(
    fail_questions: Optional[Set[str]] = None,
) -> AsyncMock:
    """Create a mock RAG service that returns canned responses.

    Parameters
    ----------
    fail_questions:
        Set of question texts for which the RAG service should raise.
    """
    fail_questions = fail_questions or set()
    mock = AsyncMock()

    async def _generate_response(query: str, user_id: str = "") -> Dict[str, Any]:
        if query in fail_questions:
            raise RuntimeError(f"RAG failure for: {query}")
        return {
            "response": f"Gold answer for: {query}",
            "sources": [
                {"document_title": "Medical Textbook", "chunk_id": "chunk-001"},
                {"document_title": "Clinical Guide", "chunk_id": "chunk-002"},
            ],
        }

    mock.generate_response = AsyncMock(side_effect=_generate_response)
    return mock


# ---------------------------------------------------------------------------
# Property 12: Evaluation set excludes training questions
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestEvaluationSetExcludesTrainingQuestions:
    """Property 12: Evaluation set excludes training questions.

    # Feature: medical-knowledge-finetuning, Property 12: Evaluation set excludes training questions

    For any training dataset and generated evaluation set, the intersection
    of training instruction texts and evaluation question texts SHALL be
    empty.

    Validates: Requirements 7.2
    """

    # ------------------------------------------------------------------
    # Core property: no overlap between training and evaluation questions
    # ------------------------------------------------------------------

    @given(
        concept_names=st.lists(
            _concept_name(),
            min_size=5,
            max_size=20,
            unique=True,
        ),
        training_fraction=st.floats(min_value=0.0, max_value=1.0),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @pytest.mark.asyncio
    async def test_no_training_questions_in_eval_set(
        self,
        concept_names: List[str],
        training_fraction: float,
    ) -> None:
        """Evaluation set must not contain any question from the training set."""
        # Build a pool of all possible questions from the templates
        all_possible_questions: List[str] = []
        types_with_templates = [t for t in EVAL_SEMANTIC_TYPES if t in _EVAL_TEMPLATES]
        for sem_type in types_with_templates:
            for template in _EVAL_TEMPLATES[sem_type]:
                for name in concept_names:
                    all_possible_questions.append(
                        template.format(concept_name=name)
                    )

        assume(len(all_possible_questions) > 0)

        # Split: some questions go into the training set
        split_idx = int(len(all_possible_questions) * training_fraction)
        training_questions: Set[str] = set(all_possible_questions[:split_idx])

        # Set up mock Neo4j to return the same concepts for every type
        concepts_by_type = {
            sem_type: list(concept_names)
            for sem_type in types_with_templates
        }
        mock_neo4j = _make_mock_neo4j(concepts_by_type)
        mock_rag = _make_mock_rag()

        config = EvaluationConfig(
            eval_set_path="",
            min_semantic_types=5,
            eval_count=50,
        )
        runner = EvaluationRunner(config, judge=AsyncMock())

        eval_set = await runner.generate_eval_set(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            training_questions=training_questions,
            count=min(50, len(all_possible_questions)),
            min_semantic_types=1,
        )

        # The core property: no overlap
        eval_question_texts = {q.question for q in eval_set.questions}
        training_normalised = {q.strip().lower() for q in training_questions}
        eval_normalised = {q.strip().lower() for q in eval_question_texts}

        overlap = training_normalised & eval_normalised
        assert overlap == set(), (
            f"Training/evaluation overlap found: {overlap}"
        )

    # ------------------------------------------------------------------
    # Property: exclusion works with case-insensitive matching
    # ------------------------------------------------------------------

    @given(
        concept_names=st.lists(
            _concept_name(),
            min_size=3,
            max_size=10,
            unique=True,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @pytest.mark.asyncio
    async def test_exclusion_is_case_insensitive(
        self,
        concept_names: List[str],
    ) -> None:
        """Training questions with different casing are still excluded."""
        types_with_templates = [t for t in EVAL_SEMANTIC_TYPES if t in _EVAL_TEMPLATES]

        # Build training set with UPPER-CASED versions of all possible questions
        training_questions: Set[str] = set()
        for sem_type in types_with_templates:
            for template in _EVAL_TEMPLATES[sem_type]:
                for name in concept_names:
                    training_questions.add(
                        template.format(concept_name=name).upper()
                    )

        assume(len(training_questions) > 0)

        concepts_by_type = {
            sem_type: list(concept_names)
            for sem_type in types_with_templates
        }
        mock_neo4j = _make_mock_neo4j(concepts_by_type)
        mock_rag = _make_mock_rag()

        config = EvaluationConfig(eval_set_path="")
        runner = EvaluationRunner(config, judge=AsyncMock())

        eval_set = await runner.generate_eval_set(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            training_questions=training_questions,
            count=50,
            min_semantic_types=1,
        )

        # Normalised comparison — no overlap allowed
        training_normalised = {q.strip().lower() for q in training_questions}
        eval_normalised = {q.question.strip().lower() for q in eval_set.questions}

        overlap = training_normalised & eval_normalised
        assert overlap == set(), (
            f"Case-insensitive overlap found: {overlap}"
        )

    # ------------------------------------------------------------------
    # Property: empty training set means no exclusions
    # ------------------------------------------------------------------

    @given(
        concept_names=st.lists(
            _concept_name(),
            min_size=3,
            max_size=10,
            unique=True,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @pytest.mark.asyncio
    async def test_empty_training_set_excludes_nothing(
        self,
        concept_names: List[str],
    ) -> None:
        """With an empty training set, all generated questions are kept."""
        types_with_templates = [t for t in EVAL_SEMANTIC_TYPES if t in _EVAL_TEMPLATES]
        concepts_by_type = {
            sem_type: list(concept_names)
            for sem_type in types_with_templates
        }
        mock_neo4j = _make_mock_neo4j(concepts_by_type)
        mock_rag = _make_mock_rag()

        config = EvaluationConfig(eval_set_path="")
        runner = EvaluationRunner(config, judge=AsyncMock())

        eval_set = await runner.generate_eval_set(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            training_questions=set(),  # empty
            count=20,
            min_semantic_types=1,
        )

        # With no training exclusions and working mocks, we should get questions
        assert len(eval_set.questions) > 0, (
            "Expected at least one evaluation question with empty training set"
        )

    # ------------------------------------------------------------------
    # Property: all training questions excluded → empty eval set
    # ------------------------------------------------------------------

    @given(
        concept_names=st.lists(
            _concept_name(),
            min_size=2,
            max_size=5,
            unique=True,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @pytest.mark.asyncio
    async def test_all_questions_in_training_yields_empty_eval(
        self,
        concept_names: List[str],
    ) -> None:
        """When every possible question is in the training set, eval set is empty."""
        from multimodal_librarian.ml.loinc_cleaner import clean_concept_name

        types_with_templates = [t for t in EVAL_SEMANTIC_TYPES if t in _EVAL_TEMPLATES]

        # Put every possible question into the training set, using
        # cleaned concept names (matching what the eval runner does).
        training_questions: Set[str] = set()
        for sem_type in types_with_templates:
            for template in _EVAL_TEMPLATES[sem_type]:
                for name in concept_names:
                    cleaned = clean_concept_name(name)
                    if cleaned:
                        training_questions.add(
                            template.format(concept_name=cleaned)
                        )
                    # Also add the raw version in case cleaning is a no-op
                    training_questions.add(
                        template.format(concept_name=name)
                    )

        concepts_by_type = {
            sem_type: list(concept_names)
            for sem_type in types_with_templates
        }
        mock_neo4j = _make_mock_neo4j(concepts_by_type)
        mock_rag = _make_mock_rag()

        config = EvaluationConfig(eval_set_path="")
        runner = EvaluationRunner(config, judge=AsyncMock())

        eval_set = await runner.generate_eval_set(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            training_questions=training_questions,
            count=50,
            min_semantic_types=1,
        )

        # Every candidate was in training → nothing should remain
        assert len(eval_set.questions) == 0, (
            f"Expected empty eval set but got {len(eval_set.questions)} questions"
        )

    # ------------------------------------------------------------------
    # Property: exclusion preserves structural validity of remaining questions
    # ------------------------------------------------------------------

    @given(
        concept_names=st.lists(
            _concept_name(),
            min_size=5,
            max_size=15,
            unique=True,
        ),
        training_fraction=st.floats(min_value=0.1, max_value=0.5),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    @pytest.mark.asyncio
    async def test_remaining_questions_are_structurally_valid(
        self,
        concept_names: List[str],
        training_fraction: float,
    ) -> None:
        """Questions surviving exclusion still have all required fields."""
        types_with_templates = [t for t in EVAL_SEMANTIC_TYPES if t in _EVAL_TEMPLATES]

        all_questions: List[str] = []
        for sem_type in types_with_templates:
            for template in _EVAL_TEMPLATES[sem_type]:
                for name in concept_names:
                    all_questions.append(template.format(concept_name=name))

        assume(len(all_questions) > 0)

        split_idx = int(len(all_questions) * training_fraction)
        training_questions: Set[str] = set(all_questions[:split_idx])

        concepts_by_type = {
            sem_type: list(concept_names)
            for sem_type in types_with_templates
        }
        mock_neo4j = _make_mock_neo4j(concepts_by_type)
        mock_rag = _make_mock_rag()

        config = EvaluationConfig(eval_set_path="")
        runner = EvaluationRunner(config, judge=AsyncMock())

        eval_set = await runner.generate_eval_set(
            rag_service=mock_rag,
            neo4j_client=mock_neo4j,
            training_questions=training_questions,
            count=50,
            min_semantic_types=1,
        )

        for q in eval_set.questions:
            assert isinstance(q, EvaluationQuestion)
            assert q.question.strip(), "Question text must be non-empty"
            assert q.gold_answer.strip(), "Gold answer must be non-empty"
            assert q.semantic_type.strip(), "Semantic type must be non-empty"
            assert len(q.source_citations) > 0, "Must have at least one citation"
            assert q.difficulty_level in (
                "single-concept",
                "multi-concept",
                "reasoning",
            ), f"Invalid difficulty: {q.difficulty_level}"


# ---------------------------------------------------------------------------
# Hypothesis strategies for Property 13
# ---------------------------------------------------------------------------


def _non_empty_text() -> st.SearchStrategy[str]:
    """Generate non-empty printable text strings."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "Zs", "P"),
        ),
        min_size=2,
        max_size=120,
    ).filter(lambda s: s.strip())


def _difficulty_level() -> st.SearchStrategy[str]:
    """Pick a valid difficulty level."""
    return st.sampled_from(list(VALID_DIFFICULTY_LEVELS))


def _source_citations() -> st.SearchStrategy[List[str]]:
    """Generate a non-empty list of citation strings."""
    return st.lists(
        _non_empty_text(),
        min_size=1,
        max_size=5,
    )


def _evaluation_question() -> st.SearchStrategy[EvaluationQuestion]:
    """Generate a random valid EvaluationQuestion."""
    return st.builds(
        EvaluationQuestion,
        question=_non_empty_text(),
        gold_answer=_non_empty_text(),
        semantic_type=_non_empty_text(),
        source_citations=_source_citations(),
        difficulty_level=_difficulty_level(),
    )


def _evaluation_set() -> st.SearchStrategy[EvaluationSet]:
    """Generate a random EvaluationSet with 1–20 questions."""
    return st.builds(
        EvaluationSet,
        questions=st.lists(
            _evaluation_question(),
            min_size=1,
            max_size=20,
        ),
        metadata=st.just({"test": True}),
    )


# ---------------------------------------------------------------------------
# Property 13: Evaluation set JSONL format
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestEvaluationSetJSONLFormat:
    """Property 13: Evaluation set JSONL format.

    # Feature: medical-knowledge-finetuning, Property 13: Evaluation set JSONL format

    For any exported evaluation set, each JSONL line SHALL contain the
    fields: question, gold_answer, semantic_type, source_citations, and
    difficulty_level — all non-empty.

    Validates: Requirements 7.5
    """

    # ------------------------------------------------------------------
    # Core property: every JSONL line has all required non-empty fields
    # ------------------------------------------------------------------

    @given(eval_set=_evaluation_set())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_exported_jsonl_lines_contain_all_required_fields(
        self,
        eval_set: EvaluationSet,
    ) -> None:
        """Each JSONL line must contain all five required fields."""
        required_fields = {
            "question",
            "gold_answer",
            "semantic_type",
            "source_citations",
            "difficulty_level",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "eval_set.jsonl"
            EvaluationRunner.export_eval_set(eval_set, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                lines = [
                    ln.strip() for ln in fh.readlines()
                    if ln.strip()
                ]

            assert len(lines) == len(eval_set.questions), (
                f"Expected {len(eval_set.questions)} lines, "
                f"got {len(lines)}"
            )

            for lineno, line in enumerate(lines, start=1):
                data = json.loads(line)
                missing = required_fields - set(data.keys())
                assert not missing, (
                    f"Line {lineno} missing fields: {missing}"
                )

    # ------------------------------------------------------------------
    # Property: all field values are non-empty
    # ------------------------------------------------------------------

    @given(eval_set=_evaluation_set())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_exported_jsonl_fields_are_non_empty(
        self,
        eval_set: EvaluationSet,
    ) -> None:
        """Every required field in each JSONL line must be non-empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "eval_set.jsonl"
            EvaluationRunner.export_eval_set(eval_set, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                lines = [
                    ln.strip() for ln in fh.readlines()
                    if ln.strip()
                ]

            for lineno, line in enumerate(lines, start=1):
                data = json.loads(line)

                assert data["question"].strip(), (
                    f"Line {lineno}: question is empty"
                )
                assert data["gold_answer"].strip(), (
                    f"Line {lineno}: gold_answer is empty"
                )
                assert data["semantic_type"].strip(), (
                    f"Line {lineno}: semantic_type is empty"
                )
                assert data["difficulty_level"].strip(), (
                    f"Line {lineno}: difficulty_level is empty"
                )

                citations = data["source_citations"]
                assert isinstance(citations, list), (
                    f"Line {lineno}: source_citations is not a list"
                )
                assert len(citations) > 0, (
                    f"Line {lineno}: source_citations is empty"
                )
                for i, cit in enumerate(citations):
                    assert isinstance(cit, str) and cit.strip(), (
                        f"Line {lineno}: citation {i} is empty"
                    )

    # ------------------------------------------------------------------
    # Property: round-trip through export → load preserves content
    # ------------------------------------------------------------------

    @given(eval_set=_evaluation_set())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_export_then_load_preserves_questions(
        self,
        eval_set: EvaluationSet,
    ) -> None:
        """Exporting then loading an eval set preserves all questions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "eval_set.jsonl"
            EvaluationRunner.export_eval_set(eval_set, output_path)
            loaded = EvaluationRunner.load_eval_set(output_path)

            assert len(loaded.questions) == len(eval_set.questions), (
                f"Expected {len(eval_set.questions)} questions, "
                f"got {len(loaded.questions)}"
            )

            for orig, loaded_q in zip(
                eval_set.questions, loaded.questions
            ):
                assert loaded_q.question == orig.question
                assert loaded_q.gold_answer == orig.gold_answer
                assert loaded_q.semantic_type == orig.semantic_type
                assert (
                    loaded_q.source_citations
                    == orig.source_citations
                )
                assert (
                    loaded_q.difficulty_level
                    == orig.difficulty_level
                )

    # ------------------------------------------------------------------
    # Property: each line is valid JSON
    # ------------------------------------------------------------------

    @given(eval_set=_evaluation_set())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_each_exported_line_is_valid_json(
        self,
        eval_set: EvaluationSet,
    ) -> None:
        """Every line in the exported JSONL must be valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "eval_set.jsonl"
            EvaluationRunner.export_eval_set(eval_set, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                for lineno, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as exc:
                        pytest.fail(
                            f"Line {lineno} is not valid JSON: "
                            f"{exc}"
                        )

    # ------------------------------------------------------------------
    # Property: difficulty_level is always a valid value
    # ------------------------------------------------------------------

    @given(eval_set=_evaluation_set())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_difficulty_level_is_valid(
        self,
        eval_set: EvaluationSet,
    ) -> None:
        """difficulty_level in each JSONL line must be a valid value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "eval_set.jsonl"
            EvaluationRunner.export_eval_set(eval_set, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                lines = [
                    ln.strip() for ln in fh.readlines()
                    if ln.strip()
                ]

            for lineno, line in enumerate(lines, start=1):
                data = json.loads(line)
                dl = data["difficulty_level"]
                assert dl in VALID_DIFFICULTY_LEVELS, (
                    f"Line {lineno}: invalid difficulty_level "
                    f"'{dl}', expected one of "
                    f"{VALID_DIFFICULTY_LEVELS}"
                )



# ---------------------------------------------------------------------------
# Hypothesis strategies for Property 15
# ---------------------------------------------------------------------------


def _similarity_score(
    min_val: float = 0.0, max_val: float = 1.0
) -> st.SearchStrategy[float]:
    """Generate a similarity score in the given range."""
    return st.floats(
        min_value=min_val,
        max_value=max_val,
        allow_nan=False,
        allow_infinity=False,
    )


# ---------------------------------------------------------------------------
# Property 15: Improvement flagging threshold
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestImprovementFlaggingThreshold:
    """Property 15: Improvement flagging threshold.

    # Feature: medical-knowledge-finetuning, Property 15: Improvement flagging threshold

    For any comparison report where the fine-tuned model's mean semantic
    similarity improvement over the base model is less than 5%, the report
    SHALL be flagged with ``flagged=True`` and contain at least one
    recommendation. When improvement is >= 5%, ``flagged`` SHALL be
    ``False``.

    Validates: Requirements 8.6
    """

    # ------------------------------------------------------------------
    # Core property: delta < 0.05 → flagged=True with recommendations
    # ------------------------------------------------------------------

    @given(
        base_sims=st.lists(
            _similarity_score(0.0, 0.95),
            min_size=1,
            max_size=20,
        ),
        small_delta=st.floats(
            min_value=-1.0,
            max_value=0.0499,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_below_threshold_is_flagged(
        self,
        base_sims: List[float],
        small_delta: float,
    ) -> None:
        """When improvement delta < 5%, report is flagged with recommendations."""
        # Build QuestionResults where win_rate yields delta < threshold
        # Use all "tie" or "base" winners to get win_rate <= 0.5
        results: List[QuestionResult] = []
        types_cycle = list(EVAL_SEMANTIC_TYPES)
        diffs = list(VALID_DIFFICULTY_LEVELS)

        for i, b_sim in enumerate(base_sims):
            results.append(
                QuestionResult(
                    question=f"Question {i}",
                    gold_answer=f"Gold answer {i}",
                    base_response=f"Base response {i}",
                    finetuned_response=f"FT response {i}",
                    base_score=ResponseScore(
                        factual_accuracy=3,
                        completeness=3,
                        clinical_relevance=3,
                        coherence=3,
                    ),
                    finetuned_score=ResponseScore(
                        factual_accuracy=3,
                        completeness=3,
                        clinical_relevance=3,
                        coherence=3,
                    ),
                    semantic_type=types_cycle[i % len(types_cycle)],
                    difficulty_level=diffs[i % len(diffs)],
                    winner="tie",
                )
            )

        runner = _make_runner(0.05)
        report = runner._build_report(results, total_questions=len(results), judge_success=len(results), judge_failure=0)

        # win_rate = 0 (all ties), improvement_delta = 0 - 0.5 = -0.5 < 0.05
        assert report.flagged is True, (
            f"Expected flagged=True when all ties (delta={report.improvement_delta:.4f}), "
            f"but got flagged={report.flagged}"
        )
        assert len(report.recommendations) >= 1, (
            f"Expected at least one recommendation when flagged, "
            f"got {len(report.recommendations)}"
        )

    # ------------------------------------------------------------------
    # Core property: delta >= 0.05 → flagged=False
    # ------------------------------------------------------------------

    @given(
        base_sims=st.lists(
            _similarity_score(0.0, 0.90),
            min_size=1,
            max_size=20,
        ),
        large_delta=st.floats(
            min_value=0.05,
            max_value=0.5,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_at_or_above_threshold_not_flagged(
        self,
        base_sims: List[float],
        large_delta: float,
    ) -> None:
        """When improvement delta >= 5%, report is NOT flagged."""
        # All winners are "finetuned" → win_rate = 1.0, delta = 0.5 >= 0.05
        results: List[QuestionResult] = []
        types_cycle = list(EVAL_SEMANTIC_TYPES)
        diffs = list(VALID_DIFFICULTY_LEVELS)

        for i, b_sim in enumerate(base_sims):
            results.append(
                QuestionResult(
                    question=f"Question {i}",
                    gold_answer=f"Gold answer {i}",
                    base_response=f"Base response {i}",
                    finetuned_response=f"FT response {i}",
                    base_score=ResponseScore(
                        factual_accuracy=2,
                        completeness=2,
                        clinical_relevance=2,
                        coherence=2,
                    ),
                    finetuned_score=ResponseScore(
                        factual_accuracy=4,
                        completeness=4,
                        clinical_relevance=4,
                        coherence=4,
                    ),
                    semantic_type=types_cycle[i % len(types_cycle)],
                    difficulty_level=diffs[i % len(diffs)],
                    winner="finetuned",
                )
            )

        runner = _make_runner(0.05)
        report = runner._build_report(results, total_questions=len(results), judge_success=len(results), judge_failure=0)

        # win_rate = 1.0, improvement_delta = 1.0 - 0.5 = 0.5 >= 0.05
        assert report.flagged is False, (
            f"Expected flagged=False when all finetuned wins "
            f"(delta={report.improvement_delta:.4f}), "
            f"but got flagged={report.flagged}"
        )

    # ------------------------------------------------------------------
    # Property: negative delta always flagged with extra recommendation
    # ------------------------------------------------------------------

    @given(
        base_sims=st.lists(
            _similarity_score(0.2, 0.9),
            min_size=1,
            max_size=15,
        ),
        negative_delta=st.floats(
            min_value=-0.5,
            max_value=-0.01,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_negative_delta_flagged_with_regression_warning(
        self,
        base_sims: List[float],
        negative_delta: float,
    ) -> None:
        """Negative improvement (regression) is always flagged with extra advice."""
        # All winners are "base" → win_rate = 0, delta = -0.5 (always negative)
        results: List[QuestionResult] = []
        types_cycle = list(EVAL_SEMANTIC_TYPES)
        diffs = list(VALID_DIFFICULTY_LEVELS)

        for i, b_sim in enumerate(base_sims):
            results.append(
                QuestionResult(
                    question=f"Question {i}",
                    gold_answer=f"Gold answer {i}",
                    base_response=f"Base response {i}",
                    finetuned_response=f"FT response {i}",
                    base_score=ResponseScore(
                        factual_accuracy=4,
                        completeness=4,
                        clinical_relevance=4,
                        coherence=4,
                    ),
                    finetuned_score=ResponseScore(
                        factual_accuracy=2,
                        completeness=2,
                        clinical_relevance=2,
                        coherence=2,
                    ),
                    semantic_type=types_cycle[i % len(types_cycle)],
                    difficulty_level=diffs[i % len(diffs)],
                    winner="base",
                )
            )

        runner = _make_runner(0.05)
        report = runner._build_report(results, total_questions=len(results), judge_success=len(results), judge_failure=0)

        # win_rate = 0, improvement_delta = -0.5 (always negative)
        assert report.flagged is True, (
            f"Expected flagged=True for negative delta={report.improvement_delta:.4f}"
        )
        assert len(report.recommendations) >= 1, (
            "Expected at least one recommendation for negative delta"
        )

        # When delta is actually negative, there should be a regression warning
        if report.improvement_delta < 0:
            regression_recs = [
                r for r in report.recommendations
                if "lower" in r.lower() or "overfit" in r.lower()
            ]
            assert len(regression_recs) >= 1, (
                f"Expected a regression-specific recommendation when "
                f"delta={report.improvement_delta:.4f} < 0, but recommendations "
                f"were: {report.recommendations}"
            )

    # ------------------------------------------------------------------
    # Property: exact boundary (delta == 0.05) → not flagged
    # ------------------------------------------------------------------

    def test_exact_threshold_not_flagged(self) -> None:
        """When improvement delta is exactly at threshold, report is NOT flagged."""
        # Construct results where win_rate yields delta >= threshold
        # With 20 questions, 11 finetuned wins → win_rate = 0.55, delta = 0.05
        results: List[QuestionResult] = []
        for i in range(20):
            winner = "finetuned" if i < 11 else "base"
            results.append(
                QuestionResult(
                    question=f"Question {i}",
                    gold_answer=f"Gold answer {i}",
                    base_response=f"Base response {i}",
                    finetuned_response=f"FT response {i}",
                    base_score=ResponseScore(
                        factual_accuracy=3,
                        completeness=3,
                        clinical_relevance=3,
                        coherence=3,
                    ),
                    finetuned_score=ResponseScore(
                        factual_accuracy=4,
                        completeness=4,
                        clinical_relevance=4,
                        coherence=4,
                    ),
                    semantic_type="Disease or Syndrome",
                    difficulty_level="single-concept",
                    winner=winner,
                )
            )

        runner = _make_runner(0.05)
        report = runner._build_report(results, total_questions=len(results), judge_success=len(results), judge_failure=0)

        # win_rate = 11/20 = 0.55, delta = 0.55 - 0.5 = 0.05, NOT < 0.05
        assert report.flagged is False, (
            f"Expected flagged=False at exact threshold, "
            f"but got flagged={report.flagged} with "
            f"delta={report.improvement_delta}"
        )

    # ------------------------------------------------------------------
    # Property: empty results → flagged with recommendation
    # ------------------------------------------------------------------

    def test_empty_results_flagged(self) -> None:
        """An empty result set should be flagged with a recommendation."""
        runner = _make_runner(0.05)
        report = runner._build_report([], total_questions=0, judge_success=0, judge_failure=0)

        assert report.flagged is True, (
            "Expected flagged=True for empty results"
        )
        assert len(report.recommendations) >= 1, (
            "Expected at least one recommendation for empty results"
        )

    # ------------------------------------------------------------------
    # Property: configurable threshold is respected
    # ------------------------------------------------------------------

    @given(
        threshold=st.floats(
            min_value=0.01,
            max_value=0.20,
            allow_nan=False,
            allow_infinity=False,
        ),
        base_sim=_similarity_score(0.3, 0.7),
        delta=st.floats(
            min_value=-0.1,
            max_value=0.25,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_configurable_threshold_respected(
        self,
        threshold: float,
        base_sim: float,
        delta: float,
    ) -> None:
        """The flagging threshold from EvaluationConfig is respected."""
        # Use winner to control improvement_delta
        # If delta >= threshold, we need win_rate >= threshold + 0.5
        # Simplify: use 2 questions, control winner to get specific win_rate
        winner = "finetuned" if delta >= 0 else "base"

        results = [
            QuestionResult(
                question="Test question",
                gold_answer="Test gold answer",
                base_response="Test base response",
                finetuned_response="Test FT response",
                base_score=ResponseScore(
                    factual_accuracy=3,
                    completeness=3,
                    clinical_relevance=3,
                    coherence=3,
                ),
                finetuned_score=ResponseScore(
                    factual_accuracy=4,
                    completeness=4,
                    clinical_relevance=4,
                    coherence=4,
                ),
                semantic_type="Disease or Syndrome",
                difficulty_level="single-concept",
                winner=winner,
            )
        ]

        runner = _make_runner(threshold)
        report = runner._build_report(results, total_questions=len(results), judge_success=len(results), judge_failure=0)

        # With 1 question: win_rate is 0 or 1, delta is -0.5 or 0.5
        actual_delta = report.improvement_delta

        if actual_delta < threshold:
            assert report.flagged is True, (
                f"Expected flagged=True when delta={actual_delta:.4f} "
                f"< threshold={threshold:.4f}"
            )
            assert len(report.recommendations) >= 1, (
                f"Expected recommendations when flagged "
                f"(delta={actual_delta:.4f}, threshold={threshold:.4f})"
            )
        else:
            assert report.flagged is False, (
                f"Expected flagged=False when delta={actual_delta:.4f} "
                f">= threshold={threshold:.4f}"
            )


# ---------------------------------------------------------------------------
# Property 6: Aggregate metrics computation
# Feature: llm-judge-evaluation, Property 6: Aggregate metrics computation
# Validates: Requirements 5.1, 5.2, 5.3, 6.1
# ---------------------------------------------------------------------------

_DIMENSION_NAMES = (
    "factual_accuracy",
    "completeness",
    "clinical_relevance",
    "coherence",
)


def _dimension_score() -> st.SearchStrategy[int]:
    """Generate a valid dimension score in [1, 5]."""
    return st.integers(min_value=1, max_value=5)


def _response_score() -> st.SearchStrategy[ResponseScore]:
    """Generate a ResponseScore with random valid dimension scores."""
    return st.builds(
        ResponseScore,
        factual_accuracy=_dimension_score(),
        completeness=_dimension_score(),
        clinical_relevance=_dimension_score(),
        coherence=_dimension_score(),
    )


def _winner_strategy() -> st.SearchStrategy[str]:
    """Generate a valid winner value."""
    return st.sampled_from(["base", "finetuned", "tie"])


def _question_result_for_aggregation() -> st.SearchStrategy[QuestionResult]:
    """Generate a QuestionResult with independently random dimension scores and winner."""
    return st.builds(
        QuestionResult,
        question=_non_empty_text(),
        gold_answer=_non_empty_text(),
        base_response=_non_empty_text(),
        finetuned_response=_non_empty_text(),
        base_score=_response_score(),
        finetuned_score=_response_score(),
        semantic_type=st.sampled_from(list(EVAL_SEMANTIC_TYPES)),
        difficulty_level=_difficulty_level(),
        winner=_winner_strategy(),
        judge_explanation=_non_empty_text(),
        position_label=st.sampled_from(["base_is_A", "base_is_B"]),
    )


def _make_runner(threshold: float = 0.05) -> EvaluationRunner:
    """Create an EvaluationRunner with a mock JudgeService for testing _build_report."""
    config = EvaluationConfig(improvement_threshold=threshold)
    mock_judge = AsyncMock()
    return EvaluationRunner(config, judge=mock_judge)


@pytest.mark.pbt
@pytest.mark.unit
class TestAggregateMetricsComputation:
    """Property 6: Aggregate metrics computation.

    # Feature: llm-judge-evaluation, Property 6: Aggregate metrics computation

    For any non-empty list of QuestionResult objects with known winners and
    dimension scores, the ComparisonReport SHALL have:
    - win_rate equal to the count of results where winner == "finetuned"
      divided by the total count
    - mean_score_delta equal to the mean of (finetuned dimension score −
      base dimension score) across all four dimensions and all results
    - improvement_delta equal to win_rate - 0.5
    - base_mean_scores and finetuned_mean_scores with per-dimension means
      matching the arithmetic mean of each dimension across all results

    Validates: Requirements 5.1, 5.2, 5.3, 6.1
    """

    # ------------------------------------------------------------------
    # Core property: win_rate = finetuned_wins / total
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_win_rate_equals_finetuned_fraction(
        self,
        results: List[QuestionResult],
    ) -> None:
        """win_rate == count(winner=='finetuned') / len(results)."""
        runner = _make_runner()
        report = runner._build_report(results)

        expected_win_count = sum(
            1 for r in results if r.winner == "finetuned"
        )
        expected_win_rate = expected_win_count / len(results)

        assert abs(report.win_rate - round(expected_win_rate, 4)) < 1e-6, (
            f"Expected win_rate={expected_win_rate:.6f}, "
            f"got {report.win_rate:.6f} "
            f"(finetuned wins: {expected_win_count}/{len(results)})"
        )

    # ------------------------------------------------------------------
    # Core property: mean_score_delta = mean(ft - base) across all
    # dimensions and all results
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_mean_score_delta_computation(
        self,
        results: List[QuestionResult],
    ) -> None:
        """mean_score_delta == mean of (ft_dim - base_dim) across all dims and results."""
        runner = _make_runner()
        report = runner._build_report(results)

        all_deltas: List[float] = []
        for r in results:
            for dim in _DIMENSION_NAMES:
                all_deltas.append(
                    float(getattr(r.finetuned_score, dim) - getattr(r.base_score, dim))
                )
        expected_delta = sum(all_deltas) / len(all_deltas)

        assert abs(report.mean_score_delta - round(expected_delta, 4)) < 1e-6, (
            f"Expected mean_score_delta={expected_delta:.6f}, "
            f"got {report.mean_score_delta:.6f}"
        )

    # ------------------------------------------------------------------
    # Core property: improvement_delta = win_rate - 0.5
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_improvement_delta_equals_win_rate_minus_half(
        self,
        results: List[QuestionResult],
    ) -> None:
        """improvement_delta == win_rate - 0.5."""
        runner = _make_runner()
        report = runner._build_report(results)

        expected_improvement = report.win_rate - 0.5

        assert abs(report.improvement_delta - round(expected_improvement, 4)) < 1e-6, (
            f"Expected improvement_delta={expected_improvement:.6f}, "
            f"got {report.improvement_delta:.6f} "
            f"(win_rate={report.win_rate:.6f})"
        )

    # ------------------------------------------------------------------
    # Core property: per-dimension mean scores are correct
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_per_dimension_mean_scores(
        self,
        results: List[QuestionResult],
    ) -> None:
        """base_mean_scores and finetuned_mean_scores match arithmetic means."""
        runner = _make_runner()
        report = runner._build_report(results)

        n = len(results)
        for dim in _DIMENSION_NAMES:
            expected_base_mean = sum(
                getattr(r.base_score, dim) for r in results
            ) / n
            expected_ft_mean = sum(
                getattr(r.finetuned_score, dim) for r in results
            ) / n

            assert dim in report.base_mean_scores, (
                f"Missing dimension '{dim}' in base_mean_scores"
            )
            assert dim in report.finetuned_mean_scores, (
                f"Missing dimension '{dim}' in finetuned_mean_scores"
            )

            assert abs(report.base_mean_scores[dim] - round(expected_base_mean, 4)) < 1e-6, (
                f"base_mean_scores[{dim}]: expected {expected_base_mean:.6f}, "
                f"got {report.base_mean_scores[dim]:.6f}"
            )
            assert abs(report.finetuned_mean_scores[dim] - round(expected_ft_mean, 4)) < 1e-6, (
                f"finetuned_mean_scores[{dim}]: expected {expected_ft_mean:.6f}, "
                f"got {report.finetuned_mean_scores[dim]:.6f}"
            )

    # ------------------------------------------------------------------
    # Property: all four dimensions are present in mean scores
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_all_dimensions_present_in_mean_scores(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Both base and finetuned mean scores contain all four dimensions."""
        runner = _make_runner()
        report = runner._build_report(results)

        for dim in _DIMENSION_NAMES:
            assert dim in report.base_mean_scores, (
                f"Missing '{dim}' in base_mean_scores: {report.base_mean_scores}"
            )
            assert dim in report.finetuned_mean_scores, (
                f"Missing '{dim}' in finetuned_mean_scores: {report.finetuned_mean_scores}"
            )

    # ------------------------------------------------------------------
    # Property: win_rate is bounded [0, 1]
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_win_rate_bounded(
        self,
        results: List[QuestionResult],
    ) -> None:
        """win_rate is always in [0, 1]."""
        runner = _make_runner()
        report = runner._build_report(results)

        assert 0.0 <= report.win_rate <= 1.0, (
            f"win_rate={report.win_rate} is outside [0, 1]"
        )

    # ------------------------------------------------------------------
    # Property: improvement_delta is bounded [-0.5, 0.5]
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_improvement_delta_bounded(
        self,
        results: List[QuestionResult],
    ) -> None:
        """improvement_delta is always in [-0.5, 0.5]."""
        runner = _make_runner()
        report = runner._build_report(results)

        assert -0.5 <= report.improvement_delta <= 0.5 + 1e-6, (
            f"improvement_delta={report.improvement_delta} is outside [-0.5, 0.5]"
        )

    # ------------------------------------------------------------------
    # Property: mean_score_delta is bounded [-4, 4]
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_mean_score_delta_bounded(
        self,
        results: List[QuestionResult],
    ) -> None:
        """mean_score_delta is bounded by the score range: [-4, 4]."""
        runner = _make_runner()
        report = runner._build_report(results)

        # Max delta per dimension is 5-1=4, min is 1-5=-4
        assert -4.0 <= report.mean_score_delta <= 4.0, (
            f"mean_score_delta={report.mean_score_delta} is outside [-4, 4]"
        )

    # ------------------------------------------------------------------
    # Property: all-finetuned-wins yields win_rate=1.0
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_all_finetuned_wins_yields_full_win_rate(
        self,
        results: List[QuestionResult],
    ) -> None:
        """When all winners are 'finetuned', win_rate == 1.0."""
        # Override all winners to finetuned
        for r in results:
            r.winner = "finetuned"

        runner = _make_runner()
        report = runner._build_report(results)

        assert abs(report.win_rate - 1.0) < 1e-6, (
            f"Expected win_rate=1.0 when all finetuned, got {report.win_rate}"
        )
        assert abs(report.improvement_delta - 0.5) < 1e-6, (
            f"Expected improvement_delta=0.5, got {report.improvement_delta}"
        )

    # ------------------------------------------------------------------
    # Property: no-finetuned-wins yields win_rate=0.0
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_no_finetuned_wins_yields_zero_win_rate(
        self,
        results: List[QuestionResult],
    ) -> None:
        """When no winners are 'finetuned', win_rate == 0.0."""
        # Override all winners to base or tie
        for r in results:
            r.winner = "base"

        runner = _make_runner()
        report = runner._build_report(results)

        assert abs(report.win_rate - 0.0) < 1e-6, (
            f"Expected win_rate=0.0 when no finetuned wins, got {report.win_rate}"
        )
        assert abs(report.improvement_delta - (-0.5)) < 1e-6, (
            f"Expected improvement_delta=-0.5, got {report.improvement_delta}"
        )

# ---------------------------------------------------------------------------
# Property 7: Breakdown computation by grouping key
# Feature: llm-judge-evaluation, Property 7: Breakdown computation by grouping key
# Validates: Requirements 5.4, 5.5
# ---------------------------------------------------------------------------


def _question_result_with_group(
    semantic_types: List[str],
    difficulty_levels: List[str],
) -> st.SearchStrategy[QuestionResult]:
    """Generate a QuestionResult drawn from the given semantic types and difficulty levels."""
    return st.builds(
        QuestionResult,
        question=_non_empty_text(),
        gold_answer=_non_empty_text(),
        base_response=_non_empty_text(),
        finetuned_response=_non_empty_text(),
        base_score=_response_score(),
        finetuned_score=_response_score(),
        semantic_type=st.sampled_from(semantic_types),
        difficulty_level=st.sampled_from(difficulty_levels),
        winner=_winner_strategy(),
        judge_explanation=_non_empty_text(),
        position_label=st.sampled_from(["base_is_A", "base_is_B"]),
    )


def _compute_expected_breakdown(
    group: List[QuestionResult],
) -> Dict[str, Any]:
    """Independently compute the expected breakdown for a group of results.

    Mirrors the logic in ``EvaluationRunner._build_report`` so the test
    can compare against the actual implementation.
    """
    n = len(group)
    win_count = sum(1 for r in group if r.winner == "finetuned")
    win_rate = win_count / n

    all_deltas: List[float] = []
    for r in group:
        for dim in _DIMENSION_NAMES:
            all_deltas.append(
                float(getattr(r.finetuned_score, dim) - getattr(r.base_score, dim))
            )
    mean_score_delta = sum(all_deltas) / len(all_deltas) if all_deltas else 0.0

    base_means: Dict[str, float] = {}
    ft_means: Dict[str, float] = {}
    for dim in _DIMENSION_NAMES:
        base_means[dim] = round(
            sum(getattr(r.base_score, dim) for r in group) / n, 4
        )
        ft_means[dim] = round(
            sum(getattr(r.finetuned_score, dim) for r in group) / n, 4
        )

    return {
        "win_rate": round(win_rate, 4),
        "mean_score_delta": round(mean_score_delta, 4),
        "base_mean_scores": base_means,
        "finetuned_mean_scores": ft_means,
        "count": float(n),
    }


@pytest.mark.pbt
@pytest.mark.unit
class TestBreakdownComputationByGroupingKey:
    """Property 7: Breakdown computation by grouping key.

    # Feature: llm-judge-evaluation, Property 7: Breakdown computation by grouping key

    For any non-empty list of QuestionResult objects with at least two
    distinct semantic types or difficulty levels, the per-semantic-type and
    per-difficulty breakdowns SHALL each contain correct win_rate,
    mean_score_delta, and count values computed from only the results in
    that group.

    Validates: Requirements 5.4, 5.5
    """

    # ------------------------------------------------------------------
    # Core property: per-semantic-type breakdown has correct win_rate
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_semantic_type_breakdown_win_rate(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Each semantic type group has correct win_rate."""
        assume(len({r.semantic_type for r in results}) >= 2)

        runner = _make_runner()
        report = runner._build_report(results)

        # Group results by semantic type
        groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            groups.setdefault(r.semantic_type, []).append(r)

        assert set(report.by_semantic_type.keys()) == set(groups.keys()), (
            f"Semantic type keys mismatch: report has {set(report.by_semantic_type.keys())}, "
            f"expected {set(groups.keys())}"
        )

        for stype, group in groups.items():
            expected = _compute_expected_breakdown(group)
            actual = report.by_semantic_type[stype]
            assert abs(actual["win_rate"] - expected["win_rate"]) < 1e-6, (
                f"Semantic type '{stype}': expected win_rate={expected['win_rate']}, "
                f"got {actual['win_rate']}"
            )

    # ------------------------------------------------------------------
    # Core property: per-semantic-type breakdown has correct mean_score_delta
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_semantic_type_breakdown_mean_score_delta(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Each semantic type group has correct mean_score_delta."""
        assume(len({r.semantic_type for r in results}) >= 2)

        runner = _make_runner()
        report = runner._build_report(results)

        groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            groups.setdefault(r.semantic_type, []).append(r)

        for stype, group in groups.items():
            expected = _compute_expected_breakdown(group)
            actual = report.by_semantic_type[stype]
            assert abs(actual["mean_score_delta"] - expected["mean_score_delta"]) < 1e-6, (
                f"Semantic type '{stype}': expected mean_score_delta="
                f"{expected['mean_score_delta']}, got {actual['mean_score_delta']}"
            )

    # ------------------------------------------------------------------
    # Core property: per-semantic-type breakdown has correct count
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_semantic_type_breakdown_count(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Each semantic type group has correct count."""
        assume(len({r.semantic_type for r in results}) >= 2)

        runner = _make_runner()
        report = runner._build_report(results)

        groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            groups.setdefault(r.semantic_type, []).append(r)

        for stype, group in groups.items():
            actual = report.by_semantic_type[stype]
            assert actual["count"] == float(len(group)), (
                f"Semantic type '{stype}': expected count={len(group)}, "
                f"got {actual['count']}"
            )

    # ------------------------------------------------------------------
    # Core property: per-semantic-type breakdown has correct per-dimension means
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_semantic_type_breakdown_dimension_means(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Each semantic type group has correct base and finetuned per-dimension means."""
        assume(len({r.semantic_type for r in results}) >= 2)

        runner = _make_runner()
        report = runner._build_report(results)

        groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            groups.setdefault(r.semantic_type, []).append(r)

        for stype, group in groups.items():
            expected = _compute_expected_breakdown(group)
            actual = report.by_semantic_type[stype]

            for dim in _DIMENSION_NAMES:
                assert abs(
                    actual["base_mean_scores"][dim] - expected["base_mean_scores"][dim]
                ) < 1e-6, (
                    f"Semantic type '{stype}', base {dim}: "
                    f"expected {expected['base_mean_scores'][dim]}, "
                    f"got {actual['base_mean_scores'][dim]}"
                )
                assert abs(
                    actual["finetuned_mean_scores"][dim]
                    - expected["finetuned_mean_scores"][dim]
                ) < 1e-6, (
                    f"Semantic type '{stype}', finetuned {dim}: "
                    f"expected {expected['finetuned_mean_scores'][dim]}, "
                    f"got {actual['finetuned_mean_scores'][dim]}"
                )

    # ------------------------------------------------------------------
    # Core property: per-difficulty breakdown has correct win_rate
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_difficulty_breakdown_win_rate(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Each difficulty group has correct win_rate."""
        assume(len({r.difficulty_level for r in results}) >= 2)

        runner = _make_runner()
        report = runner._build_report(results)

        groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            groups.setdefault(r.difficulty_level, []).append(r)

        assert set(report.by_difficulty.keys()) == set(groups.keys()), (
            f"Difficulty keys mismatch: report has {set(report.by_difficulty.keys())}, "
            f"expected {set(groups.keys())}"
        )

        for dlevel, group in groups.items():
            expected = _compute_expected_breakdown(group)
            actual = report.by_difficulty[dlevel]
            assert abs(actual["win_rate"] - expected["win_rate"]) < 1e-6, (
                f"Difficulty '{dlevel}': expected win_rate={expected['win_rate']}, "
                f"got {actual['win_rate']}"
            )

    # ------------------------------------------------------------------
    # Core property: per-difficulty breakdown has correct mean_score_delta
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_difficulty_breakdown_mean_score_delta(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Each difficulty group has correct mean_score_delta."""
        assume(len({r.difficulty_level for r in results}) >= 2)

        runner = _make_runner()
        report = runner._build_report(results)

        groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            groups.setdefault(r.difficulty_level, []).append(r)

        for dlevel, group in groups.items():
            expected = _compute_expected_breakdown(group)
            actual = report.by_difficulty[dlevel]
            assert abs(actual["mean_score_delta"] - expected["mean_score_delta"]) < 1e-6, (
                f"Difficulty '{dlevel}': expected mean_score_delta="
                f"{expected['mean_score_delta']}, got {actual['mean_score_delta']}"
            )

    # ------------------------------------------------------------------
    # Core property: per-difficulty breakdown has correct count
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_difficulty_breakdown_count(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Each difficulty group has correct count."""
        assume(len({r.difficulty_level for r in results}) >= 2)

        runner = _make_runner()
        report = runner._build_report(results)

        groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            groups.setdefault(r.difficulty_level, []).append(r)

        for dlevel, group in groups.items():
            actual = report.by_difficulty[dlevel]
            assert actual["count"] == float(len(group)), (
                f"Difficulty '{dlevel}': expected count={len(group)}, "
                f"got {actual['count']}"
            )

    # ------------------------------------------------------------------
    # Core property: per-difficulty breakdown has correct per-dimension means
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_difficulty_breakdown_dimension_means(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Each difficulty group has correct base and finetuned per-dimension means."""
        assume(len({r.difficulty_level for r in results}) >= 2)

        runner = _make_runner()
        report = runner._build_report(results)

        groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            groups.setdefault(r.difficulty_level, []).append(r)

        for dlevel, group in groups.items():
            expected = _compute_expected_breakdown(group)
            actual = report.by_difficulty[dlevel]

            for dim in _DIMENSION_NAMES:
                assert abs(
                    actual["base_mean_scores"][dim] - expected["base_mean_scores"][dim]
                ) < 1e-6, (
                    f"Difficulty '{dlevel}', base {dim}: "
                    f"expected {expected['base_mean_scores'][dim]}, "
                    f"got {actual['base_mean_scores'][dim]}"
                )
                assert abs(
                    actual["finetuned_mean_scores"][dim]
                    - expected["finetuned_mean_scores"][dim]
                ) < 1e-6, (
                    f"Difficulty '{dlevel}', finetuned {dim}: "
                    f"expected {expected['finetuned_mean_scores'][dim]}, "
                    f"got {actual['finetuned_mean_scores'][dim]}"
                )

    # ------------------------------------------------------------------
    # Property: group counts sum to total results
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=list(EVAL_SEMANTIC_TYPES[:4]),
                difficulty_levels=list(VALID_DIFFICULTY_LEVELS),
            ),
            min_size=2,
            max_size=30,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_group_counts_sum_to_total(
        self,
        results: List[QuestionResult],
    ) -> None:
        """Sum of counts across all groups equals total number of results."""
        runner = _make_runner()
        report = runner._build_report(results)

        type_total = sum(
            int(v["count"]) for v in report.by_semantic_type.values()
        )
        assert type_total == len(results), (
            f"Semantic type counts sum to {type_total}, expected {len(results)}"
        )

        diff_total = sum(
            int(v["count"]) for v in report.by_difficulty.values()
        )
        assert diff_total == len(results), (
            f"Difficulty counts sum to {diff_total}, expected {len(results)}"
        )

    # ------------------------------------------------------------------
    # Property: single-group results produce one breakdown entry
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_with_group(
                semantic_types=["Disease or Syndrome"],
                difficulty_levels=["reasoning"],
            ),
            min_size=1,
            max_size=15,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_single_group_produces_one_entry(
        self,
        results: List[QuestionResult],
    ) -> None:
        """When all results share the same group key, breakdown has exactly one entry."""
        runner = _make_runner()
        report = runner._build_report(results)

        assert len(report.by_semantic_type) == 1, (
            f"Expected 1 semantic type entry, got {len(report.by_semantic_type)}"
        )
        assert "Disease or Syndrome" in report.by_semantic_type

        assert len(report.by_difficulty) == 1, (
            f"Expected 1 difficulty entry, got {len(report.by_difficulty)}"
        )
        assert "reasoning" in report.by_difficulty

        # The single group's metrics should match the overall metrics
        st_entry = report.by_semantic_type["Disease or Syndrome"]
        assert abs(st_entry["win_rate"] - report.win_rate) < 1e-6
        assert abs(st_entry["mean_score_delta"] - report.mean_score_delta) < 1e-6


# ---------------------------------------------------------------------------
# Property 8: Flagging threshold
# Feature: llm-judge-evaluation, Property 8: Flagging threshold
# Validates: Requirements 6.2
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestFlaggingThreshold:
    """Property 8: Flagging threshold.

    # Feature: llm-judge-evaluation, Property 8: Flagging threshold

    For any improvement_delta and configured Pipeline_Threshold, the
    flagged field SHALL be True if and only if improvement_delta < threshold
    (when high failure rate is not a factor).

    Validates: Requirements 6.2
    """

    # ------------------------------------------------------------------
    # Core property: flagged iff improvement_delta < threshold
    # ------------------------------------------------------------------

    @given(
        threshold=st.floats(
            min_value=0.0,
            max_value=0.5,
            allow_nan=False,
            allow_infinity=False,
        ),
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_flagged_iff_delta_below_threshold(
        self,
        threshold: float,
        results: List[QuestionResult],
    ) -> None:
        """flagged == (improvement_delta < threshold) when no high failure rate."""
        runner = _make_runner(threshold=threshold)
        # Pass judge_failure=0 so high_failure_rate is never triggered
        report = runner._build_report(
            results, total_questions=len(results), judge_success=len(results), judge_failure=0
        )

        expected_flagged = report.improvement_delta < threshold
        assert report.flagged is expected_flagged, (
            f"Expected flagged={expected_flagged} when "
            f"improvement_delta={report.improvement_delta:.4f} and "
            f"threshold={threshold:.4f}, but got flagged={report.flagged}"
        )

    # ------------------------------------------------------------------
    # Property: delta below threshold always produces flagged=True
    # ------------------------------------------------------------------

    @given(
        threshold=st.floats(
            min_value=0.01,
            max_value=0.5,
            allow_nan=False,
            allow_infinity=False,
        ),
        n_results=st.integers(min_value=1, max_value=30),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_all_ties_always_flagged_for_positive_threshold(
        self,
        threshold: float,
        n_results: int,
    ) -> None:
        """All-tie results yield delta=-0.5, which is always below any positive threshold."""
        results = [
            QuestionResult(
                question=f"Q{i}",
                gold_answer=f"A{i}",
                base_response=f"B{i}",
                finetuned_response=f"F{i}",
                base_score=ResponseScore(
                    factual_accuracy=3, completeness=3,
                    clinical_relevance=3, coherence=3,
                ),
                finetuned_score=ResponseScore(
                    factual_accuracy=3, completeness=3,
                    clinical_relevance=3, coherence=3,
                ),
                semantic_type="Disease or Syndrome",
                difficulty_level="single-concept",
                winner="tie",
            )
            for i in range(n_results)
        ]

        runner = _make_runner(threshold=threshold)
        report = runner._build_report(
            results, total_questions=n_results, judge_success=n_results, judge_failure=0
        )

        # win_rate=0, delta=-0.5, always below any positive threshold
        assert report.improvement_delta < 0, (
            f"Expected negative delta for all ties, got {report.improvement_delta}"
        )
        assert report.flagged is True, (
            f"Expected flagged=True for all-tie results with threshold={threshold}"
        )
        assert len(report.recommendations) >= 1, (
            "Expected at least one recommendation when flagged"
        )

    # ------------------------------------------------------------------
    # Property: delta at or above threshold produces flagged=False
    # ------------------------------------------------------------------

    @given(
        threshold=st.floats(
            min_value=0.0,
            max_value=0.49,
            allow_nan=False,
            allow_infinity=False,
        ),
        n_results=st.integers(min_value=1, max_value=30),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_all_finetuned_wins_not_flagged(
        self,
        threshold: float,
        n_results: int,
    ) -> None:
        """All-finetuned-wins yield delta=0.5, which is above any threshold < 0.5."""
        results = [
            QuestionResult(
                question=f"Q{i}",
                gold_answer=f"A{i}",
                base_response=f"B{i}",
                finetuned_response=f"F{i}",
                base_score=ResponseScore(
                    factual_accuracy=2, completeness=2,
                    clinical_relevance=2, coherence=2,
                ),
                finetuned_score=ResponseScore(
                    factual_accuracy=4, completeness=4,
                    clinical_relevance=4, coherence=4,
                ),
                semantic_type="Disease or Syndrome",
                difficulty_level="single-concept",
                winner="finetuned",
            )
            for i in range(n_results)
        ]

        runner = _make_runner(threshold=threshold)
        report = runner._build_report(
            results, total_questions=n_results, judge_success=n_results, judge_failure=0
        )

        # win_rate=1.0, delta=0.5, always >= any threshold <= 0.49
        assert report.improvement_delta >= threshold, (
            f"Expected delta >= threshold, got delta={report.improvement_delta}, "
            f"threshold={threshold}"
        )
        assert report.flagged is False, (
            f"Expected flagged=False for all-finetuned-wins with threshold={threshold}"
        )

    # ------------------------------------------------------------------
    # Property: threshold=0 means only negative deltas are flagged
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_zero_threshold_flags_only_negative_delta(
        self,
        results: List[QuestionResult],
    ) -> None:
        """With threshold=0, flagged is True only when improvement_delta < 0."""
        runner = _make_runner(threshold=0.0)
        report = runner._build_report(
            results, total_questions=len(results), judge_success=len(results), judge_failure=0
        )

        if report.improvement_delta < 0:
            assert report.flagged is True, (
                f"Expected flagged=True when delta={report.improvement_delta:.4f} < 0 "
                f"with threshold=0"
            )
        else:
            assert report.flagged is False, (
                f"Expected flagged=False when delta={report.improvement_delta:.4f} >= 0 "
                f"with threshold=0"
            )

    # ------------------------------------------------------------------
    # Property: flagged implies recommendations are non-empty
    # ------------------------------------------------------------------

    @given(
        threshold=st.floats(
            min_value=0.01,
            max_value=0.5,
            allow_nan=False,
            allow_infinity=False,
        ),
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_flagged_implies_nonempty_recommendations(
        self,
        threshold: float,
        results: List[QuestionResult],
    ) -> None:
        """When flagged due to threshold, recommendations must be non-empty."""
        runner = _make_runner(threshold=threshold)
        report = runner._build_report(
            results, total_questions=len(results), judge_success=len(results), judge_failure=0
        )

        if report.flagged:
            assert len(report.recommendations) >= 1, (
                f"Expected non-empty recommendations when flagged=True "
                f"(delta={report.improvement_delta:.4f}, threshold={threshold:.4f})"
            )

    # ------------------------------------------------------------------
    # Property: monotonicity — raising threshold can only increase flagging
    # ------------------------------------------------------------------

    @given(
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=15,
        ),
        threshold_low=st.floats(
            min_value=0.0,
            max_value=0.25,
            allow_nan=False,
            allow_infinity=False,
        ),
        threshold_high=st.floats(
            min_value=0.25,
            max_value=0.5,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_higher_threshold_never_unflag(
        self,
        results: List[QuestionResult],
        threshold_low: float,
        threshold_high: float,
    ) -> None:
        """If flagged at a lower threshold, must also be flagged at a higher threshold."""
        assume(threshold_low <= threshold_high)

        runner_low = _make_runner(threshold=threshold_low)
        report_low = runner_low._build_report(
            results, total_questions=len(results), judge_success=len(results), judge_failure=0
        )

        runner_high = _make_runner(threshold=threshold_high)
        report_high = runner_high._build_report(
            results, total_questions=len(results), judge_success=len(results), judge_failure=0
        )

        if report_low.flagged:
            assert report_high.flagged, (
                f"Flagged at threshold={threshold_low:.4f} "
                f"(delta={report_low.improvement_delta:.4f}) but NOT flagged "
                f"at higher threshold={threshold_high:.4f} "
                f"(delta={report_high.improvement_delta:.4f})"
            )

# ---------------------------------------------------------------------------
# Property 9: JSON report contains all required fields
# Feature: llm-judge-evaluation, Property 9: JSON report contains all required fields
# Validates: Requirements 7.2, 7.3, 7.4
# ---------------------------------------------------------------------------

_JSON_TOP_LEVEL_KEYS = {
    "win_rate",
    "mean_score_delta",
    "improvement_delta",
    "flagged",
    "recommendations",
    "by_semantic_type",
    "by_difficulty",
    "judge_stats",
    "results",
}

_JSON_RESULT_ENTRY_KEYS = {
    "question",
    "gold_answer",
    "base_response",
    "finetuned_response",
    "base_score",
    "finetuned_score",
    "semantic_type",
    "difficulty_level",
    "winner",
    "judge_explanation",
    "position_label",
}

_JSON_SCORE_KEYS = {
    "factual_accuracy",
    "completeness",
    "clinical_relevance",
    "coherence",
}

_JSON_BY_TYPE_ENTRY_KEYS = {
    "win_rate",
    "mean_score_delta",
    "base_mean_scores",
    "finetuned_mean_scores",
    "count",
}


def _comparison_report_for_json() -> st.SearchStrategy[ComparisonReport]:
    """Generate a ComparisonReport by building results and running _build_report.

    This ensures the report is internally consistent (metrics match results)
    rather than constructing arbitrary field values.
    """
    return st.lists(
        _question_result_for_aggregation(),
        min_size=1,
        max_size=15,
    ).map(lambda results: _make_runner()._build_report(
        results,
        total_questions=len(results),
        judge_success=len(results),
        judge_failure=0,
    ))


@pytest.mark.pbt
@pytest.mark.unit
class TestJSONReportRequiredFields:
    """Property 9: JSON report contains all required fields.

    # Feature: llm-judge-evaluation, Property 9: JSON report contains all required fields

    For any valid ComparisonReport, exporting to JSON and loading the result
    SHALL produce a dict containing all required top-level keys (win_rate,
    mean_score_delta, improvement_delta, flagged, recommendations,
    by_semantic_type, by_difficulty, judge_stats, results), with results
    having the same length as the input and each entry containing all
    per-question fields.

    Validates: Requirements 7.2, 7.3, 7.4
    """

    # ------------------------------------------------------------------
    # Core property: all required top-level keys are present
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_has_all_top_level_keys(
        self,
        report: ComparisonReport,
    ) -> None:
        """Exported JSON must contain all nine required top-level keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        missing = _JSON_TOP_LEVEL_KEYS - set(data.keys())
        assert not missing, (
            f"JSON report missing top-level keys: {missing}"
        )

    # ------------------------------------------------------------------
    # Property: results array length matches input
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_results_length_matches_input(
        self,
        report: ComparisonReport,
    ) -> None:
        """The results array in JSON must have the same length as the report's results."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        assert len(data["results"]) == len(report.results), (
            f"Expected {len(report.results)} result entries, "
            f"got {len(data['results'])}"
        )

    # ------------------------------------------------------------------
    # Property: each result entry has all per-question fields
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_result_entries_have_all_fields(
        self,
        report: ComparisonReport,
    ) -> None:
        """Every entry in the results array must contain all per-question fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        for idx, entry in enumerate(data["results"]):
            missing = _JSON_RESULT_ENTRY_KEYS - set(entry.keys())
            assert not missing, (
                f"Result entry {idx} missing fields: {missing}"
            )

    # ------------------------------------------------------------------
    # Property: base_score and finetuned_score contain all dimension keys
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_score_dicts_have_all_dimension_keys(
        self,
        report: ComparisonReport,
    ) -> None:
        """base_score and finetuned_score in each result must have all four dimension keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        for idx, entry in enumerate(data["results"]):
            for score_key in ("base_score", "finetuned_score"):
                score = entry[score_key]
                missing = _JSON_SCORE_KEYS - set(score.keys())
                assert not missing, (
                    f"Result entry {idx} {score_key} missing dimension keys: {missing}"
                )
                # Verify scores are integers in [1, 5]
                for dim in _JSON_SCORE_KEYS:
                    val = score[dim]
                    assert isinstance(val, int) and 1 <= val <= 5, (
                        f"Result entry {idx} {score_key}.{dim}={val} "
                        f"is not an integer in [1, 5]"
                    )

    # ------------------------------------------------------------------
    # Property: by_semantic_type entries have required sub-fields (Req 7.3)
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_by_semantic_type_entries_have_required_fields(
        self,
        report: ComparisonReport,
    ) -> None:
        """Each by_semantic_type entry must have win_rate, mean_score_delta,
        base_mean_scores, finetuned_mean_scores, and count."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        by_type = data["by_semantic_type"]
        assert len(by_type) > 0, (
            "by_semantic_type should have at least one entry for non-empty results"
        )
        for stype, entry in by_type.items():
            missing = _JSON_BY_TYPE_ENTRY_KEYS - set(entry.keys())
            assert not missing, (
                f"by_semantic_type['{stype}'] missing fields: {missing}"
            )

    # ------------------------------------------------------------------
    # Property: by_difficulty entries have required sub-fields
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_by_difficulty_entries_have_required_fields(
        self,
        report: ComparisonReport,
    ) -> None:
        """Each by_difficulty entry must have the same sub-fields as by_semantic_type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        by_diff = data["by_difficulty"]
        assert len(by_diff) > 0, (
            "by_difficulty should have at least one entry for non-empty results"
        )
        for dlevel, entry in by_diff.items():
            missing = _JSON_BY_TYPE_ENTRY_KEYS - set(entry.keys())
            assert not missing, (
                f"by_difficulty['{dlevel}'] missing fields: {missing}"
            )

    # ------------------------------------------------------------------
    # Property: judge_stats has required fields (Req 7.5)
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_judge_stats_has_required_fields(
        self,
        report: ComparisonReport,
    ) -> None:
        """judge_stats must contain total_questions, successful_judgments,
        failed_judgments, and judge_model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        judge_stats = data["judge_stats"]
        required_stats_keys = {
            "total_questions",
            "successful_judgments",
            "failed_judgments",
            "judge_model",
        }
        missing = required_stats_keys - set(judge_stats.keys())
        assert not missing, (
            f"judge_stats missing fields: {missing}"
        )

    # ------------------------------------------------------------------
    # Property: result field values match the original report data
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_result_values_match_report(
        self,
        report: ComparisonReport,
    ) -> None:
        """Field values in the JSON results must match the original ComparisonReport."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        for idx, (entry, orig) in enumerate(
            zip(data["results"], report.results)
        ):
            assert entry["question"] == orig.question, (
                f"Result {idx}: question mismatch"
            )
            assert entry["gold_answer"] == orig.gold_answer, (
                f"Result {idx}: gold_answer mismatch"
            )
            assert entry["winner"] == orig.winner, (
                f"Result {idx}: winner mismatch"
            )
            assert entry["semantic_type"] == orig.semantic_type, (
                f"Result {idx}: semantic_type mismatch"
            )
            assert entry["difficulty_level"] == orig.difficulty_level, (
                f"Result {idx}: difficulty_level mismatch"
            )
            assert entry["position_label"] == orig.position_label, (
                f"Result {idx}: position_label mismatch"
            )

    # ------------------------------------------------------------------
    # Property: top-level numeric values match the report
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_top_level_values_match_report(
        self,
        report: ComparisonReport,
    ) -> None:
        """Top-level numeric and boolean values in JSON must match the report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)

        assert abs(data["win_rate"] - report.win_rate) < 1e-6, (
            f"win_rate mismatch: JSON={data['win_rate']}, report={report.win_rate}"
        )
        assert abs(data["mean_score_delta"] - report.mean_score_delta) < 1e-6, (
            f"mean_score_delta mismatch: JSON={data['mean_score_delta']}, "
            f"report={report.mean_score_delta}"
        )
        assert abs(data["improvement_delta"] - report.improvement_delta) < 1e-6, (
            f"improvement_delta mismatch: JSON={data['improvement_delta']}, "
            f"report={report.improvement_delta}"
        )
        assert data["flagged"] is report.flagged, (
            f"flagged mismatch: JSON={data['flagged']}, report={report.flagged}"
        )
        assert data["recommendations"] == report.recommendations, (
            f"recommendations mismatch"
        )

    # ------------------------------------------------------------------
    # Property: exported JSON is valid JSON (parseable)
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_json_output_is_valid_json(
        self,
        report: ComparisonReport,
    ) -> None:
        """The exported file must be valid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.json"
            EvaluationRunner._export_json_report(report, output_path)

            with open(output_path, "r", encoding="utf-8") as fh:
                raw = fh.read()

        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Exported JSON is not valid: {exc}")


# ---------------------------------------------------------------------------
# Strategy reuse note: _comparison_report_for_json generates internally
# consistent ComparisonReport objects via _build_report, so we reuse it here.
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestMarkdownReportContainsReportValues:
    """Property 10: Markdown report contains report values.

    # Feature: llm-judge-evaluation, Property 10: Markdown report contains report values

    For any valid ComparisonReport with at least one result, the exported
    Markdown string SHALL contain the string representations of win_rate,
    mean_score_delta, improvement_delta, the flagged status, and the total
    question count.

    Validates: Requirements 8.2
    """

    # ------------------------------------------------------------------
    # Helper: export markdown and return the content as a string
    # ------------------------------------------------------------------

    @staticmethod
    def _export_and_read(report: ComparisonReport) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "comparison_report.md"
            EvaluationRunner._export_markdown_report(report, output_path)
            return output_path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Core property: win_rate value appears in the Markdown
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_contains_win_rate(
        self,
        report: ComparisonReport,
    ) -> None:
        """The Markdown report must contain the formatted win_rate value."""
        md = self._export_and_read(report)
        expected = f"{report.win_rate:.4f}"
        assert expected in md, (
            f"win_rate {expected} not found in Markdown report"
        )

    # ------------------------------------------------------------------
    # Core property: mean_score_delta value appears in the Markdown
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_contains_mean_score_delta(
        self,
        report: ComparisonReport,
    ) -> None:
        """The Markdown report must contain the formatted mean_score_delta value."""
        md = self._export_and_read(report)
        expected = f"{report.mean_score_delta:.4f}"
        assert expected in md, (
            f"mean_score_delta {expected} not found in Markdown report"
        )

    # ------------------------------------------------------------------
    # Core property: improvement_delta value appears in the Markdown
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_contains_improvement_delta(
        self,
        report: ComparisonReport,
    ) -> None:
        """The Markdown report must contain the formatted improvement_delta value."""
        md = self._export_and_read(report)
        expected = f"{report.improvement_delta:.4f}"
        assert expected in md, (
            f"improvement_delta {expected} not found in Markdown report"
        )

    # ------------------------------------------------------------------
    # Core property: flagged status appears in the Markdown
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_contains_flagged_status(
        self,
        report: ComparisonReport,
    ) -> None:
        """The Markdown report must contain the flagged status as 'Yes' or 'No'."""
        md = self._export_and_read(report)
        expected_flag = "Yes" if report.flagged else "No"
        assert expected_flag in md, (
            f"Flagged status '{expected_flag}' not found in Markdown report"
        )

    # ------------------------------------------------------------------
    # Core property: total question count appears in the Markdown
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_contains_total_questions(
        self,
        report: ComparisonReport,
    ) -> None:
        """The Markdown report must contain the total question count."""
        md = self._export_and_read(report)
        expected = str(len(report.results))
        assert expected in md, (
            f"Total questions count '{expected}' not found in Markdown report"
        )

    # ------------------------------------------------------------------
    # Combined property: all five summary values present in one check
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_contains_all_summary_values(
        self,
        report: ComparisonReport,
    ) -> None:
        """All five summary values must appear in the Markdown report."""
        md = self._export_and_read(report)

        checks = {
            "win_rate": f"{report.win_rate:.4f}",
            "mean_score_delta": f"{report.mean_score_delta:.4f}",
            "improvement_delta": f"{report.improvement_delta:.4f}",
            "flagged": "Yes" if report.flagged else "No",
            "total_questions": str(len(report.results)),
        }

        missing = [
            name for name, value in checks.items() if value not in md
        ]
        assert not missing, (
            f"Markdown report missing summary values: {missing}. "
            f"Expected: {checks}"
        )

    # ------------------------------------------------------------------
    # Property: Markdown report contains the summary table header
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_contains_summary_section(
        self,
        report: ComparisonReport,
    ) -> None:
        """The Markdown report must contain the Summary section header."""
        md = self._export_and_read(report)
        assert "## Summary" in md, "Markdown report missing '## Summary' header"

    # ------------------------------------------------------------------
    # Property: Markdown report contains per-dimension breakdown
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_contains_dimension_breakdown(
        self,
        report: ComparisonReport,
    ) -> None:
        """The Markdown report must contain the per-dimension breakdown section
        when dimension mean scores are present."""
        md = self._export_and_read(report)
        if report.base_mean_scores and report.finetuned_mean_scores:
            assert "## Per-Dimension Breakdown" in md, (
                "Markdown report missing '## Per-Dimension Breakdown' header"
            )
            for dim in [
                "Factual Accuracy",
                "Completeness",
                "Clinical Relevance",
                "Coherence",
            ]:
                assert dim in md, (
                    f"Dimension '{dim}' not found in Markdown breakdown"
                )

    # ------------------------------------------------------------------
    # Property: per-dimension mean values appear in the Markdown
    # ------------------------------------------------------------------

    @given(report=_comparison_report_for_json())
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_markdown_dimension_values_match_report(
        self,
        report: ComparisonReport,
    ) -> None:
        """Per-dimension base and finetuned mean values must appear in the Markdown."""
        md = self._export_and_read(report)
        if report.base_mean_scores and report.finetuned_mean_scores:
            for dim in [
                "factual_accuracy",
                "completeness",
                "clinical_relevance",
                "coherence",
            ]:
                base_val = report.base_mean_scores.get(dim, 0.0)
                ft_val = report.finetuned_mean_scores.get(dim, 0.0)
                assert f"{base_val:.4f}" in md, (
                    f"Base mean for {dim} ({base_val:.4f}) not in Markdown"
                )
                assert f"{ft_val:.4f}" in md, (
                    f"Finetuned mean for {dim} ({ft_val:.4f}) not in Markdown"
                )


# ---------------------------------------------------------------------------
# Property 13: High failure rate triggers flagging
# Feature: llm-judge-evaluation, Property 13: High failure rate triggers flagging
# Validates: Requirements 10.4
# ---------------------------------------------------------------------------


@pytest.mark.pbt
@pytest.mark.unit
class TestHighFailureRateTriggersFlag:
    """Property 13: High failure rate triggers flagging.

    # Feature: llm-judge-evaluation, Property 13: High failure rate triggers flagging

    For any evaluation run where the number of failed judge calls exceeds
    50% of total questions, the ComparisonReport SHALL have flagged set to
    True and recommendations SHALL contain at least one entry mentioning
    the failure rate.

    Validates: Requirements 10.4
    """

    # ------------------------------------------------------------------
    # Core property: >50% failures always triggers flagged=True
    # ------------------------------------------------------------------

    @given(
        total_questions=st.integers(min_value=1, max_value=100),
        failure_fraction=st.floats(
            min_value=0.51,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
        threshold=st.floats(
            min_value=-0.5,
            max_value=0.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_high_failure_rate_sets_flagged_true(
        self,
        total_questions: int,
        failure_fraction: float,
        results: List[QuestionResult],
        threshold: float,
    ) -> None:
        """When >50% of judge calls fail, flagged must be True regardless of delta."""
        judge_failure = max(1, int(total_questions * failure_fraction))
        # Ensure failure count actually exceeds 50%
        assume(judge_failure > total_questions * 0.5)
        judge_success = total_questions - judge_failure

        runner = _make_runner(threshold=threshold)
        report = runner._build_report(
            results,
            total_questions=total_questions,
            judge_success=judge_success,
            judge_failure=judge_failure,
        )

        assert report.flagged is True, (
            f"Expected flagged=True when {judge_failure}/{total_questions} "
            f"({judge_failure / total_questions:.0%}) judge calls failed "
            f"(>50% threshold), but got flagged=False"
        )

    # ------------------------------------------------------------------
    # Property: high failure rate recommendation mentions failure rate
    # ------------------------------------------------------------------

    @given(
        total_questions=st.integers(min_value=2, max_value=100),
        failure_fraction=st.floats(
            min_value=0.51,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_high_failure_rate_recommendation_mentions_failure(
        self,
        total_questions: int,
        failure_fraction: float,
        results: List[QuestionResult],
    ) -> None:
        """Recommendations must mention the failure count when >50% fail."""
        judge_failure = max(1, int(total_questions * failure_fraction))
        assume(judge_failure > total_questions * 0.5)
        judge_success = total_questions - judge_failure

        runner = _make_runner(threshold=0.0)
        report = runner._build_report(
            results,
            total_questions=total_questions,
            judge_success=judge_success,
            judge_failure=judge_failure,
        )

        failure_mentioned = any(
            "failure" in rec.lower() or "failed" in rec.lower()
            for rec in report.recommendations
        )
        assert failure_mentioned, (
            f"Expected at least one recommendation mentioning failure rate "
            f"when {judge_failure}/{total_questions} judge calls failed, "
            f"but recommendations were: {report.recommendations}"
        )

    # ------------------------------------------------------------------
    # Property: exactly 50% failures does NOT trigger high-failure flagging
    # ------------------------------------------------------------------

    @given(
        half=st.integers(min_value=1, max_value=50),
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_exactly_half_failures_no_high_failure_flag(
        self,
        half: int,
        results: List[QuestionResult],
    ) -> None:
        """Exactly 50% failures should NOT trigger high-failure-rate flagging.

        The condition is strictly >50%, so exactly half should not trigger it.
        We use a very negative threshold so delta-based flagging doesn't interfere.
        """
        total_questions = half * 2  # even number, exactly 50%
        judge_failure = half
        judge_success = half

        # Use a threshold that won't trigger delta-based flagging
        # (all-finetuned-wins gives delta=0.5, threshold=-1.0 won't flag)
        all_finetuned_results = [
            QuestionResult(
                question=f"Q{i}",
                gold_answer=f"A{i}",
                base_response=f"B{i}",
                finetuned_response=f"F{i}",
                base_score=ResponseScore(
                    factual_accuracy=2, completeness=2,
                    clinical_relevance=2, coherence=2,
                ),
                finetuned_score=ResponseScore(
                    factual_accuracy=4, completeness=4,
                    clinical_relevance=4, coherence=4,
                ),
                semantic_type="Disease or Syndrome",
                difficulty_level="single-concept",
                winner="finetuned",
            )
            for i in range(max(1, len(results)))
        ]

        runner = _make_runner(threshold=-1.0)
        report = runner._build_report(
            all_finetuned_results,
            total_questions=total_questions,
            judge_success=judge_success,
            judge_failure=judge_failure,
        )

        # With threshold=-1.0 and all finetuned wins (delta=0.5),
        # delta-based flagging won't trigger. Only high_failure_rate matters.
        assert report.flagged is False, (
            f"Expected flagged=False when exactly {judge_failure}/{total_questions} "
            f"(50%) judge calls failed (threshold is strictly >50%), "
            f"but got flagged=True"
        )

    # ------------------------------------------------------------------
    # Property: no failures never triggers high-failure flagging
    # ------------------------------------------------------------------

    @given(
        total_questions=st.integers(min_value=1, max_value=100),
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=20,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_zero_failures_no_high_failure_flag(
        self,
        total_questions: int,
        results: List[QuestionResult],
    ) -> None:
        """Zero failures should never trigger high-failure-rate flagging."""
        # Use all-finetuned-wins with very negative threshold to isolate
        all_finetuned_results = [
            QuestionResult(
                question=f"Q{i}",
                gold_answer=f"A{i}",
                base_response=f"B{i}",
                finetuned_response=f"F{i}",
                base_score=ResponseScore(
                    factual_accuracy=2, completeness=2,
                    clinical_relevance=2, coherence=2,
                ),
                finetuned_score=ResponseScore(
                    factual_accuracy=4, completeness=4,
                    clinical_relevance=4, coherence=4,
                ),
                semantic_type="Disease or Syndrome",
                difficulty_level="single-concept",
                winner="finetuned",
            )
            for i in range(max(1, len(results)))
        ]

        runner = _make_runner(threshold=-1.0)
        report = runner._build_report(
            all_finetuned_results,
            total_questions=total_questions,
            judge_success=total_questions,
            judge_failure=0,
        )

        assert report.flagged is False, (
            f"Expected flagged=False with zero failures and threshold=-1.0, "
            f"but got flagged=True"
        )

        # No failure-related recommendation should be present
        failure_recs = [
            rec for rec in report.recommendations
            if "failure" in rec.lower() or "failed" in rec.lower()
        ]
        assert len(failure_recs) == 0, (
            f"Expected no failure-related recommendations with zero failures, "
            f"but found: {failure_recs}"
        )

    # ------------------------------------------------------------------
    # Property: high failure rate flagging is independent of delta
    # ------------------------------------------------------------------

    @given(
        total_questions=st.integers(min_value=2, max_value=50),
        failure_fraction=st.floats(
            min_value=0.51,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_high_failure_flags_even_with_perfect_delta(
        self,
        total_questions: int,
        failure_fraction: float,
    ) -> None:
        """Even with all finetuned wins (best possible delta), >50% failures still flags."""
        judge_failure = max(1, int(total_questions * failure_fraction))
        assume(judge_failure > total_questions * 0.5)
        judge_success = total_questions - judge_failure

        # All finetuned wins → delta = 0.5 (best possible)
        results = [
            QuestionResult(
                question=f"Q{i}",
                gold_answer=f"A{i}",
                base_response=f"B{i}",
                finetuned_response=f"F{i}",
                base_score=ResponseScore(
                    factual_accuracy=1, completeness=1,
                    clinical_relevance=1, coherence=1,
                ),
                finetuned_score=ResponseScore(
                    factual_accuracy=5, completeness=5,
                    clinical_relevance=5, coherence=5,
                ),
                semantic_type="Disease or Syndrome",
                difficulty_level="single-concept",
                winner="finetuned",
            )
            for i in range(5)
        ]

        # Use threshold=-1.0 so delta-based flagging won't trigger
        runner = _make_runner(threshold=-1.0)
        report = runner._build_report(
            results,
            total_questions=total_questions,
            judge_success=judge_success,
            judge_failure=judge_failure,
        )

        assert report.flagged is True, (
            f"Expected flagged=True due to high failure rate "
            f"({judge_failure}/{total_questions}) even with perfect delta, "
            f"but got flagged=False"
        )

    # ------------------------------------------------------------------
    # Property: judge_stats reflects the failure counts passed in
    # ------------------------------------------------------------------

    @given(
        total_questions=st.integers(min_value=1, max_value=100),
        failure_fraction=st.floats(
            min_value=0.0,
            max_value=1.0,
            allow_nan=False,
            allow_infinity=False,
        ),
        results=st.lists(
            _question_result_for_aggregation(),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_judge_stats_reflect_failure_counts(
        self,
        total_questions: int,
        failure_fraction: float,
        results: List[QuestionResult],
    ) -> None:
        """judge_stats in the report must reflect the failure counts passed to _build_report."""
        judge_failure = int(total_questions * failure_fraction)
        judge_success = total_questions - judge_failure

        runner = _make_runner()
        report = runner._build_report(
            results,
            total_questions=total_questions,
            judge_success=judge_success,
            judge_failure=judge_failure,
        )

        assert report.judge_stats["total_questions"] == total_questions
        assert report.judge_stats["successful_judgments"] == judge_success
        assert report.judge_stats["failed_judgments"] == judge_failure
