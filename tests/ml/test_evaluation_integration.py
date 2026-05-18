"""
Integration test for the full evaluate() pipeline.

Mocks both Ollama (subprocess) and DeepSeek (API) to run the complete
EvaluationRunner.evaluate() flow end-to-end, verifying that JSON and
Markdown reports are produced with the correct structure.

Requirements: 7.1, 7.2, 8.1
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from multimodal_librarian.ml.evaluation_runner import EvaluationRunner
from multimodal_librarian.ml.judge_service import JudgeService
from multimodal_librarian.ml.models import (
    EvaluationConfig,
    EvaluationQuestion,
    EvaluationSet,
)
from multimodal_librarian.services.ai_service import AIResponse

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Sample evaluation questions spanning multiple semantic types and difficulties
SAMPLE_EVAL_QUESTIONS = [
    EvaluationQuestion(
        question="What is the mechanism of action of Aspirin?",
        gold_answer="Aspirin irreversibly inhibits cyclooxygenase (COX) enzymes.",
        semantic_type="Pharmacologic Substance",
        source_citations=["Medical Textbook (chunk-001)"],
        difficulty_level="reasoning",
    ),
    EvaluationQuestion(
        question="What are the diagnostic criteria for Diabetes Mellitus?",
        gold_answer="Fasting glucose >= 126 mg/dL or HbA1c >= 6.5%.",
        semantic_type="Disease or Syndrome",
        source_citations=["Clinical Guide (chunk-002)"],
        difficulty_level="multi-concept",
    ),
    EvaluationQuestion(
        question="What is the clinical utility of Complete Blood Count?",
        gold_answer="CBC evaluates overall health and detects disorders.",
        semantic_type="Diagnostic Procedure",
        source_citations=["Lab Manual (chunk-003)"],
        difficulty_level="single-concept",
    ),
]


def _make_judge_json(
    winner: str = "A",
    a_scores: Dict[str, int] | None = None,
    b_scores: Dict[str, int] | None = None,
) -> str:
    """Build a valid judge JSON response string."""
    a = a_scores or {
        "factual_accuracy": 4,
        "completeness": 4,
        "clinical_relevance": 5,
        "coherence": 4,
    }
    b = b_scores or {
        "factual_accuracy": 3,
        "completeness": 3,
        "clinical_relevance": 3,
        "coherence": 3,
    }
    return json.dumps(
        {
            "response_a_scores": a,
            "response_b_scores": b,
            "winner": winner,
            "explanation": f"Response {winner} is better overall.",
        }
    )


def _write_eval_set(questions: List[EvaluationQuestion], path: Path) -> None:
    """Write evaluation questions to a JSONL file."""
    eval_set = EvaluationSet(questions=questions, metadata={"test": True})
    EvaluationRunner.export_eval_set(eval_set, path)


def _make_ai_response(content: str) -> AIResponse:
    """Create an AIResponse with the given content."""
    return AIResponse(
        content=content,
        provider="deepseek",
        model="deepseek-chat",
        tokens_used=100,
        processing_time_ms=50,
        confidence_score=1.0,
        metadata={"finish_reason": "stop"},
    )


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFullEvaluationPipeline:
    """Integration test: mock Ollama + DeepSeek, run full evaluate().

    Verifies that JSON and Markdown reports are produced with the
    correct structure and content.
    """

    @pytest.mark.asyncio
    async def test_evaluate_produces_json_and_markdown_reports(self) -> None:
        """Full pipeline produces both report files with correct structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            eval_set_path = tmpdir_path / "eval_set.jsonl"
            output_dir = tmpdir_path / "output"

            _write_eval_set(SAMPLE_EVAL_QUESTIONS, eval_set_path)

            # Mock DeepSeek: return valid judge JSON for every call.
            # Alternate winners to get a mix of results.
            judge_responses = [
                _make_ai_response(_make_judge_json(winner="A")),
                _make_ai_response(_make_judge_json(winner="B")),
                _make_ai_response(_make_judge_json(winner="tie")),
            ]
            mock_deepseek = AsyncMock()
            mock_deepseek.generate_response = AsyncMock(
                side_effect=judge_responses
            )

            judge = JudgeService(
                deepseek_service=mock_deepseek,
                max_retries=2,
                temperature=0.1,
            )

            config = EvaluationConfig(
                output_dir=str(output_dir),
                improvement_threshold=0.05,
            )
            runner = EvaluationRunner(config, judge=judge)

            # Mock Ollama subprocess calls: base and finetuned for each question
            ollama_responses = []
            for q in SAMPLE_EVAL_QUESTIONS:
                ollama_responses.append(f"Base answer for: {q.question}")
                ollama_responses.append(f"Finetuned answer for: {q.question}")

            mock_subprocess_results = []
            for resp_text in ollama_responses:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = resp_text
                mock_result.stderr = ""
                mock_subprocess_results.append(mock_result)

            with patch(
                "multimodal_librarian.ml.evaluation_runner.subprocess.run",
                side_effect=mock_subprocess_results,
            ):
                # Seed random so position assignment is deterministic
                with patch(
                    "multimodal_librarian.ml.judge_service.random.random",
                    side_effect=[0.3, 0.7, 0.3],  # A, B, A positions
                ):
                    report = await runner.evaluate(
                        eval_set_path=eval_set_path,
                        base_model="llama3.2:3b",
                        finetuned_model="librarian-medical-3b",
                    )

            # ---- Verify report object ----
            assert len(report.results) == 3
            assert report.judge_stats["total_questions"] == 3
            assert report.judge_stats["successful_judgments"] == 3
            assert report.judge_stats["failed_judgments"] == 0

            # ---- Verify JSON report ----
            json_path = output_dir / "comparison_report.json"
            assert json_path.exists(), "JSON report file not created"

            with open(json_path, "r", encoding="utf-8") as fh:
                json_data = json.load(fh)

            # Required top-level fields (Req 7.2)
            required_top_level = {
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
            assert required_top_level.issubset(set(json_data.keys())), (
                f"Missing top-level keys: "
                f"{required_top_level - set(json_data.keys())}"
            )

            # Results array length matches
            assert len(json_data["results"]) == 3

            # Each result has all required per-question fields (Req 7.4)
            per_question_fields = {
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
            for i, result_entry in enumerate(json_data["results"]):
                missing = per_question_fields - set(result_entry.keys())
                assert not missing, (
                    f"Result {i} missing fields: {missing}"
                )

                # Score dicts have all four dimensions
                for score_key in ("base_score", "finetuned_score"):
                    score = result_entry[score_key]
                    for dim in (
                        "factual_accuracy",
                        "completeness",
                        "clinical_relevance",
                        "coherence",
                    ):
                        assert dim in score, (
                            f"Result {i} {score_key} missing '{dim}'"
                        )
                        assert 1 <= score[dim] <= 5

                # Winner is valid
                assert result_entry["winner"] in (
                    "base",
                    "finetuned",
                    "tie",
                )

                # Position label is valid
                assert result_entry["position_label"] in (
                    "base_is_A",
                    "base_is_B",
                )

            # judge_stats has required fields (Req 7.5)
            js = json_data["judge_stats"]
            assert "total_questions" in js
            assert "successful_judgments" in js
            assert "failed_judgments" in js
            assert "judge_model" in js

            # by_semantic_type has entries for each type in the eval set
            for sem_type in ("Pharmacologic Substance", "Disease or Syndrome", "Diagnostic Procedure"):
                assert sem_type in json_data["by_semantic_type"], (
                    f"Missing semantic type '{sem_type}' in breakdown"
                )
                entry = json_data["by_semantic_type"][sem_type]
                assert "win_rate" in entry
                assert "mean_score_delta" in entry
                assert "count" in entry

            # by_difficulty has entries
            for diff in ("reasoning", "multi-concept", "single-concept"):
                assert diff in json_data["by_difficulty"], (
                    f"Missing difficulty '{diff}' in breakdown"
                )

            # Numeric fields are reasonable
            assert 0.0 <= json_data["win_rate"] <= 1.0
            assert isinstance(json_data["flagged"], bool)
            assert isinstance(json_data["improvement_delta"], float)

            # ---- Verify Markdown report ----
            md_path = output_dir / "comparison_report.md"
            assert md_path.exists(), "Markdown report file not created"

            md_content = md_path.read_text(encoding="utf-8")

            # Summary table present (Req 8.2)
            assert "Win Rate" in md_content
            assert "Mean Score Delta" in md_content
            assert "Improvement Delta" in md_content
            assert "Flagged" in md_content
            assert "Total Questions" in md_content

            # Per-dimension breakdown (Req 8.3)
            assert "Per-Dimension Breakdown" in md_content
            assert "Factual Accuracy" in md_content
            assert "Completeness" in md_content
            assert "Clinical Relevance" in md_content
            assert "Coherence" in md_content

            # Semantic type breakdown (Req 8.4)
            assert "Semantic Type" in md_content
            assert "Pharmacologic Substance" in md_content

            # Difficulty breakdown (Req 8.5)
            assert "Difficulty" in md_content
            assert "reasoning" in md_content

    @pytest.mark.asyncio
    async def test_evaluate_handles_partial_judge_failures(self) -> None:
        """Pipeline continues when some judge calls fail after retries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            eval_set_path = tmpdir_path / "eval_set.jsonl"
            output_dir = tmpdir_path / "output"

            _write_eval_set(SAMPLE_EVAL_QUESTIONS, eval_set_path)

            # First question: valid response
            # Second question: 3 unparseable responses (1 + 2 retries)
            # Third question: valid response
            mock_deepseek = AsyncMock()
            mock_deepseek.generate_response = AsyncMock(
                side_effect=[
                    # Q1: success
                    _make_ai_response(_make_judge_json(winner="A")),
                    # Q2: 3 failures (initial + 2 retries)
                    _make_ai_response("This is not valid JSON at all"),
                    _make_ai_response("Still not JSON {broken"),
                    _make_ai_response("Nope, still broken"),
                    # Q3: success
                    _make_ai_response(_make_judge_json(winner="B")),
                ]
            )

            judge = JudgeService(
                deepseek_service=mock_deepseek,
                max_retries=2,
                temperature=0.1,
            )

            config = EvaluationConfig(
                output_dir=str(output_dir),
                improvement_threshold=0.05,
            )
            runner = EvaluationRunner(config, judge=judge)

            # 6 Ollama calls: 2 per question (base + finetuned)
            mock_subprocess_results = []
            for i in range(6):
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = f"Model response {i}"
                mock_result.stderr = ""
                mock_subprocess_results.append(mock_result)

            with patch(
                "multimodal_librarian.ml.evaluation_runner.subprocess.run",
                side_effect=mock_subprocess_results,
            ):
                report = await runner.evaluate(
                    eval_set_path=eval_set_path,
                    base_model="llama3.2:3b",
                    finetuned_model="librarian-medical-3b",
                )

            # 2 out of 3 questions succeeded
            assert len(report.results) == 2
            assert report.judge_stats["successful_judgments"] == 2
            assert report.judge_stats["failed_judgments"] == 1

            # Reports are still produced
            assert (output_dir / "comparison_report.json").exists()
            assert (output_dir / "comparison_report.md").exists()

    @pytest.mark.asyncio
    async def test_evaluate_handles_ollama_failure(self) -> None:
        """Pipeline skips questions when Ollama fails for a model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            eval_set_path = tmpdir_path / "eval_set.jsonl"
            output_dir = tmpdir_path / "output"

            # Use only 2 questions for simplicity
            _write_eval_set(SAMPLE_EVAL_QUESTIONS[:2], eval_set_path)

            mock_deepseek = AsyncMock()
            mock_deepseek.generate_response = AsyncMock(
                return_value=_make_ai_response(_make_judge_json(winner="A"))
            )

            judge = JudgeService(
                deepseek_service=mock_deepseek,
                max_retries=2,
                temperature=0.1,
            )

            config = EvaluationConfig(
                output_dir=str(output_dir),
                improvement_threshold=0.05,
            )
            runner = EvaluationRunner(config, judge=judge)

            # Q1 base: success, Q1 finetuned: fail (Ollama error)
            # Q2 base: success, Q2 finetuned: success
            mock_results = []
            # Q1 base: success
            ok_result = MagicMock()
            ok_result.returncode = 0
            ok_result.stdout = "Base answer Q1"
            ok_result.stderr = ""
            mock_results.append(ok_result)
            # Q1 finetuned: Ollama model not found
            fail_result = MagicMock()
            fail_result.returncode = 1
            fail_result.stdout = ""
            fail_result.stderr = "Error: model 'librarian-medical-3b' not found"
            mock_results.append(fail_result)
            # Q2 base: success
            ok_result2 = MagicMock()
            ok_result2.returncode = 0
            ok_result2.stdout = "Base answer Q2"
            ok_result2.stderr = ""
            mock_results.append(ok_result2)
            # Q2 finetuned: success
            ok_result3 = MagicMock()
            ok_result3.returncode = 0
            ok_result3.stdout = "Finetuned answer Q2"
            ok_result3.stderr = ""
            mock_results.append(ok_result3)

            with patch(
                "multimodal_librarian.ml.evaluation_runner.subprocess.run",
                side_effect=mock_results,
            ):
                report = await runner.evaluate(
                    eval_set_path=eval_set_path,
                    base_model="llama3.2:3b",
                    finetuned_model="librarian-medical-3b",
                )

            # Q1 skipped due to Ollama failure, Q2 succeeded
            assert len(report.results) == 1
            assert report.judge_stats["successful_judgments"] == 1

            # Reports still produced
            assert (output_dir / "comparison_report.json").exists()
            assert (output_dir / "comparison_report.md").exists()

    @pytest.mark.asyncio
    async def test_evaluate_json_report_semantic_type_breakdown_structure(
        self,
    ) -> None:
        """by_semantic_type entries have all required fields (Req 7.3)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            eval_set_path = tmpdir_path / "eval_set.jsonl"
            output_dir = tmpdir_path / "output"

            _write_eval_set(SAMPLE_EVAL_QUESTIONS, eval_set_path)

            mock_deepseek = AsyncMock()
            mock_deepseek.generate_response = AsyncMock(
                return_value=_make_ai_response(_make_judge_json(winner="A"))
            )

            judge = JudgeService(
                deepseek_service=mock_deepseek,
                max_retries=2,
                temperature=0.1,
            )

            config = EvaluationConfig(
                output_dir=str(output_dir),
                improvement_threshold=0.05,
            )
            runner = EvaluationRunner(config, judge=judge)

            mock_subprocess_results = []
            for i in range(6):
                r = MagicMock()
                r.returncode = 0
                r.stdout = f"Response {i}"
                r.stderr = ""
                mock_subprocess_results.append(r)

            with patch(
                "multimodal_librarian.ml.evaluation_runner.subprocess.run",
                side_effect=mock_subprocess_results,
            ):
                await runner.evaluate(
                    eval_set_path=eval_set_path,
                    base_model="llama3.2:3b",
                    finetuned_model="librarian-medical-3b",
                )

            json_path = output_dir / "comparison_report.json"
            with open(json_path, "r", encoding="utf-8") as fh:
                json_data = json.load(fh)

            # Each semantic type entry must have the required fields (Req 7.3)
            required_breakdown_fields = {
                "win_rate",
                "mean_score_delta",
                "base_mean_scores",
                "finetuned_mean_scores",
                "count",
            }
            for stype, entry in json_data["by_semantic_type"].items():
                missing = required_breakdown_fields - set(entry.keys())
                assert not missing, (
                    f"Semantic type '{stype}' missing fields: {missing}"
                )

                # Mean score dicts have all four dimensions
                for scores_key in ("base_mean_scores", "finetuned_mean_scores"):
                    scores = entry[scores_key]
                    for dim in (
                        "factual_accuracy",
                        "completeness",
                        "clinical_relevance",
                        "coherence",
                    ):
                        assert dim in scores, (
                            f"{stype} {scores_key} missing '{dim}'"
                        )

    @pytest.mark.asyncio
    async def test_evaluate_empty_eval_set_raises(self) -> None:
        """evaluate() raises ValueError for an empty eval set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            eval_set_path = tmpdir_path / "eval_set.jsonl"
            output_dir = tmpdir_path / "output"

            # Write an empty JSONL file
            eval_set_path.write_text("")

            mock_deepseek = AsyncMock()
            judge = JudgeService(
                deepseek_service=mock_deepseek,
                max_retries=2,
                temperature=0.1,
            )

            config = EvaluationConfig(
                output_dir=str(output_dir),
                improvement_threshold=0.05,
            )
            runner = EvaluationRunner(config, judge=judge)

            with pytest.raises(ValueError, match="contains no questions"):
                await runner.evaluate(
                    eval_set_path=eval_set_path,
                    base_model="llama3.2:3b",
                    finetuned_model="librarian-medical-3b",
                )

    @pytest.mark.asyncio
    async def test_evaluate_all_judge_failures_produces_flagged_report(
        self,
    ) -> None:
        """When all judge calls fail, report is flagged with high failure rate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            eval_set_path = tmpdir_path / "eval_set.jsonl"
            output_dir = tmpdir_path / "output"

            # Use 2 questions
            _write_eval_set(SAMPLE_EVAL_QUESTIONS[:2], eval_set_path)

            # All judge calls return unparseable responses
            mock_deepseek = AsyncMock()
            mock_deepseek.generate_response = AsyncMock(
                return_value=_make_ai_response("not json")
            )

            judge = JudgeService(
                deepseek_service=mock_deepseek,
                max_retries=2,
                temperature=0.1,
            )

            config = EvaluationConfig(
                output_dir=str(output_dir),
                improvement_threshold=0.05,
            )
            runner = EvaluationRunner(config, judge=judge)

            mock_subprocess_results = []
            for i in range(4):  # 2 questions × 2 models
                r = MagicMock()
                r.returncode = 0
                r.stdout = f"Response {i}"
                r.stderr = ""
                mock_subprocess_results.append(r)

            with patch(
                "multimodal_librarian.ml.evaluation_runner.subprocess.run",
                side_effect=mock_subprocess_results,
            ):
                report = await runner.evaluate(
                    eval_set_path=eval_set_path,
                    base_model="llama3.2:3b",
                    finetuned_model="librarian-medical-3b",
                )

            # No results since all judge calls failed
            assert len(report.results) == 0
            assert report.flagged is True
            assert report.judge_stats["failed_judgments"] == 2
            assert report.judge_stats["successful_judgments"] == 0

            # Reports are still produced (even if empty)
            assert (output_dir / "comparison_report.json").exists()
            assert (output_dir / "comparison_report.md").exists()

            # When all results are empty, the report includes a
            # recommendation about having no results to analyse
            assert len(report.recommendations) > 0, (
                "Expected at least one recommendation when all judge calls fail"
            )
