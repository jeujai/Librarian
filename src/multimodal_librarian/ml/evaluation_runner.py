"""
Evaluation Runner for Before/After Model Comparison.

Generates a curated evaluation question set with RAG-generated gold answers,
runs both the base and fine-tuned models against it via Ollama, and scores
responses using an LLM-as-judge approach via DeepSeek.

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
"""

from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .judge_service import JudgeParseError, JudgeService
from .loinc_cleaner import clean_concept_name, is_loinc_coded
from .models import (
    ComparisonReport,
    EvaluationConfig,
    EvaluationQuestion,
    EvaluationSet,
    QuestionResult,
    ResponseScore,
)
from .qlora_trainer import _SYSTEM_PROMPT, build_inference_user_message

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Similarity scoring helper
# ---------------------------------------------------------------------------


def _load_embedding_model(model_name: str):
    """Lazily load a sentence-transformers model for similarity scoring.

    Returns the SentenceTransformer instance, or None if the library
    is unavailable.
    """
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except ImportError:
        logger.warning(
            "sentence-transformers not installed; "
            "similarity scoring will be skipped."
        )
        return None
    except Exception as exc:
        logger.warning(
            "Failed to load embedding model '%s': %s. "
            "Similarity scoring will be skipped.",
            model_name,
            exc,
        )
        return None


def _compute_similarity(
    model, texts_a: List[str], texts_b: List[str]
) -> List[float]:
    """Compute pairwise cosine similarities between two lists of texts.

    Uses the sentence-transformers model to encode both lists and
    returns a list of cosine similarity scores (one per pair).
    """
    import numpy as np

    embeddings_a = model.encode(texts_a, normalize_embeddings=True)
    embeddings_b = model.encode(texts_b, normalize_embeddings=True)

    # Pairwise cosine similarity (dot product of normalized vectors)
    similarities = np.sum(embeddings_a * embeddings_b, axis=1)
    return [float(s) for s in similarities]

# ---------------------------------------------------------------------------
# Clinical semantic types used for evaluation question generation
# ---------------------------------------------------------------------------

EVAL_SEMANTIC_TYPES: List[str] = [
    "Pharmacologic Substance",
    "Disease or Syndrome",
    "Therapeutic or Preventive Procedure",
    "Sign or Symptom",
    "Diagnostic Procedure",
    "Body Part, Organ, or Organ Component",
    "Clinical Attribute",
    "Laboratory or Test Result",
    "Pathologic Function",
    "Neoplastic Process",
]

# ---------------------------------------------------------------------------
# Question templates for evaluation (per semantic type)
# ---------------------------------------------------------------------------

_EVAL_TEMPLATES: Dict[str, List[str]] = {
    "Pharmacologic Substance": [
        "How does {concept_name} work in the body?",
        "What is {concept_name} typically prescribed for?",
        "What side effects should I watch for with {concept_name}?",
    ],
    "Disease or Syndrome": [
        "What causes {concept_name} at a biological level?",
        "How do doctors diagnose {concept_name}?",
        "What are the treatment options for {concept_name}?",
    ],
    "Therapeutic or Preventive Procedure": [
        "When would a doctor recommend {concept_name}?",
        "What are the risks of {concept_name}?",
        "Can you walk me through how {concept_name} is done?",
    ],
    "Sign or Symptom": [
        "What conditions might cause {concept_name}?",
        "How would a doctor evaluate {concept_name}?",
        "What else could {concept_name} be a sign of?",
    ],
    "Diagnostic Procedure": [
        "What can {concept_name} tell us clinically?",
        "What are the limitations of {concept_name}?",
        "How should I interpret results from {concept_name}?",
    ],
    "Body Part, Organ, or Organ Component": [
        "What is the structure and function of {concept_name}?",
        "What diseases commonly affect {concept_name}?",
    ],
    "Clinical Attribute": [
        "Why is {concept_name} clinically significant?",
        "How is {concept_name} measured and what do the values mean?",
    ],
    "Laboratory or Test Result": [
        "What does an abnormal {concept_name} result suggest?",
        "What factors can influence {concept_name} results?",
    ],
    "Pathologic Function": [
        "What is the underlying mechanism behind {concept_name}?",
        "What symptoms does {concept_name} typically cause?",
    ],
    "Neoplastic Process": [
        "What are the risk factors for developing {concept_name}?",
        "What is the standard treatment approach for {concept_name}?",
    ],
}

# Cypher query to fetch UMLS concepts by semantic type for evaluation
_EVAL_CONCEPTS_QUERY = (
    "MATCH (c:UMLSConcept)-[:HAS_SEMANTIC_TYPE]->(s:UMLSSemanticType) "
    "WHERE s.type_name = $semantic_type "
    "RETURN c.preferred_name AS preferred_name, c.cui AS cui "
    "ORDER BY rand() "
    "LIMIT $limit"
)

# Difficulty classification heuristics
_REASONING_KEYWORDS = [
    "mechanism", "pathophysiology", "how", "why", "relationship",
    "interaction", "differential", "compared",
]
_MULTI_CONCEPT_KEYWORDS = [
    "associated with", "commonly", "factors", "complications",
    "treatment options", "conditions",
]


# ---------------------------------------------------------------------------
# Module-level helper functions
# ---------------------------------------------------------------------------


def _classify_difficulty(question: str) -> str:
    """Classify a question's difficulty level.

    Returns one of: ``"single-concept"``, ``"multi-concept"``, ``"reasoning"``.
    """
    q_lower = question.lower()
    if any(kw in q_lower for kw in _REASONING_KEYWORDS):
        return "reasoning"
    if any(kw in q_lower for kw in _MULTI_CONCEPT_KEYWORDS):
        return "multi-concept"
    return "single-concept"


def _extract_response_text(rag_response: Any) -> str:
    """Extract the response text from a RAG response object."""
    text = getattr(rag_response, "response", None)
    if text is None and isinstance(rag_response, dict):
        text = rag_response.get("response", "")
    return text or ""


def _extract_citations(rag_response: Any) -> List[str]:
    """Extract citation strings from a RAG response.

    Returns a list of ``"document_title (chunk_id)"`` strings.
    """
    sources = getattr(rag_response, "sources", None)
    if sources is None and isinstance(rag_response, dict):
        sources = rag_response.get("sources", [])
    if not sources:
        return []

    citations: List[str] = []
    for src in sources:
        title = getattr(src, "document_title", None)
        if title is None and isinstance(src, dict):
            title = src.get("document_title", "")
        chunk_id = getattr(src, "chunk_id", None)
        if chunk_id is None and isinstance(src, dict):
            chunk_id = src.get("chunk_id", "")
        if title:
            citation = f"{title} ({chunk_id})" if chunk_id else title
            citations.append(citation)
    return citations


def _extract_context(rag_response: Any) -> str:
    """Extract source chunk content from a RAG response for eval context.

    Concatenates the content of retrieved source chunks so the
    evaluation prompt can include the same context the model was
    trained with.
    """
    sources = getattr(rag_response, "sources", None)
    if sources is None and isinstance(rag_response, dict):
        sources = rag_response.get("sources", [])
    if not sources:
        return ""

    parts: List[str] = []
    for i, src in enumerate(sources, 1):
        # CitationSource uses 'excerpt' for chunk text; fall back to
        # 'content' for forward compatibility with other response types.
        content = getattr(src, "excerpt", None) or getattr(src, "content", None)
        if content is None and isinstance(src, dict):
            content = src.get("excerpt", "") or src.get("content", "")
        if content and content.strip():
            parts.append(f"[Source {i}] {content.strip()}")
    return "\n\n".join(parts)


def _query_ollama(
    model: str,
    user_message: str,
    system_prompt: str = _SYSTEM_PROMPT,
) -> str:
    """Send a prompt to an Ollama model and return the response text.

    Accepts an explicit ``system_prompt`` and ``user_message`` so the
    caller controls prompt construction and cannot diverge from the
    training pipeline's formatting. Both components are combined into a
    single Ollama prompt (system framing, two newlines, user content)
    matching the Llama 3 chat template's system → user flow.

    By default, ``system_prompt`` is the same ``_SYSTEM_PROMPT`` constant
    used by ``qlora_trainer.format_chat_message`` so training and
    evaluation share the same system message (clause 3.5).

    Uses ``ollama run`` via subprocess so no extra Python client is
    needed. Raises ``RuntimeError`` when the model is not found or
    Ollama is unreachable.

    Args:
        model: The Ollama model tag to invoke.
        user_message: The user-message content to send. Callers should
            build this via ``build_inference_user_message`` so it is
            byte-equal to what training produced for the same pair.
        system_prompt: The system framing to prepend. Defaults to the
            shared ``_SYSTEM_PROMPT``.

    Returns:
        The model's stdout response text, stripped.
    """
    # Combine system and user components with a blank-line separator so
    # the model sees the system framing first, matching the chat-template
    # ordering used during training.
    full_prompt = f"{system_prompt}\n\n{user_message}"

    try:
        result = subprocess.run(
            ["ollama", "run", model, full_prompt],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "Ollama CLI not found. Install Ollama and ensure it is on PATH."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Ollama timed out generating a response with model '{model}'."
        )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not found" in stderr.lower() or "pull" in stderr.lower():
            raise RuntimeError(
                f"Ollama model '{model}' not found. "
                f"Run 'ollama pull {model}' or 'ollama create {model}' first."
            )
        raise RuntimeError(
            f"Ollama returned exit code {result.returncode}: {stderr}"
        )

    return result.stdout.strip()


# ---------------------------------------------------------------------------
# EvaluationRunner
# ---------------------------------------------------------------------------


class EvaluationRunner:
    """Before/after model evaluation with gold answers.

    Generates a curated evaluation set of medical questions, runs them
    through both the base and fine-tuned models via Ollama, scores
    responses using an LLM-as-judge approach via DeepSeek, and produces
    a comparison report.

    Scoring uses the ``JudgeService`` which sends each response pair to
    DeepSeek for evaluation on four clinical dimensions (factual accuracy,
    completeness, clinical relevance, coherence) on a 1–5 integer scale,
    with randomised A/B ordering to prevent position bias.
    """

    def __init__(
        self,
        config: EvaluationConfig,
        judge: Optional[JudgeService] = None,
    ) -> None:
        self._config = config
        self._judge = judge

    # ------------------------------------------------------------------
    # Evaluation set generation
    # ------------------------------------------------------------------

    async def generate_eval_set(
        self,
        rag_service: Any,
        neo4j_client: Any,
        training_questions: Set[str],
        count: int = 50,
        min_semantic_types: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EvaluationSet:
        """Generate an evaluation question set with gold answers.

        Selects *count* questions spanning at least *min_semantic_types*
        UMLS semantic types, excludes any question that appears in the
        training dataset, generates gold answers via the RAG service,
        and replaces failed questions with alternatives from the same
        semantic type.

        Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
        """
        # Normalise training questions for exclusion check (Req 7.2)
        training_normalised: Set[str] = {
            q.strip().lower() for q in training_questions
        }

        # Determine how many questions per semantic type
        types_to_use = EVAL_SEMANTIC_TYPES[:max(min_semantic_types, 5)]
        per_type = max(count // len(types_to_use), 1)
        # Fetch extra candidates to allow for failures / exclusions
        fetch_per_type = per_type * 3

        questions: List[EvaluationQuestion] = []
        type_counts: Dict[str, int] = {}

        for sem_type in types_to_use:
            if len(questions) >= count:
                break

            templates = _EVAL_TEMPLATES.get(sem_type, [])
            if not templates:
                continue

            # Fetch concepts from Neo4j
            try:
                results = await neo4j_client.execute_query(
                    _EVAL_CONCEPTS_QUERY,
                    {"semantic_type": sem_type, "limit": fetch_per_type},
                )
            except Exception as exc:
                logger.warning(
                    "Failed to fetch concepts for type '%s': %s",
                    sem_type,
                    exc,
                )
                continue

            if not results:
                continue

            type_added = 0
            for i, record in enumerate(results):
                if len(questions) >= count:
                    break
                if type_added >= per_type:
                    break

                preferred_name = (
                    record.get("preferred_name", "")
                    if isinstance(record, dict)
                    else getattr(record, "preferred_name", "")
                )
                if not preferred_name:
                    continue

                # Clean LOINC-coded terms from concept names so eval
                # questions match the conversational training distribution.
                preferred_name = clean_concept_name(preferred_name)
                if not preferred_name:
                    continue

                template = templates[i % len(templates)]
                question_text = template.format(concept_name=preferred_name)

                # Exclude training questions (Req 7.2)
                if question_text.strip().lower() in training_normalised:
                    continue

                # Generate gold answer via RAG (Req 7.3)
                try:
                    rag_response = await rag_service.generate_response(
                        query=question_text,
                        user_id="ml-evaluation-pipeline",
                    )
                except Exception as exc:
                    logger.warning(
                        "RAG failed for eval question '%s': %s",
                        question_text[:80],
                        exc,
                    )
                    continue

                gold_text = _extract_response_text(rag_response)
                if not gold_text.strip():
                    continue

                citations = _extract_citations(rag_response)
                if not citations:
                    # Req 7.4: replace with alternative
                    continue

                difficulty = _classify_difficulty(question_text)

                questions.append(
                    EvaluationQuestion(
                        question=question_text,
                        gold_answer=gold_text,
                        semantic_type=sem_type,
                        source_citations=citations,
                        difficulty_level=difficulty,
                        context=_extract_context(rag_response),
                    )
                )
                type_added += 1
                type_counts[sem_type] = type_counts.get(sem_type, 0) + 1

                if progress_callback is not None:
                    progress_callback(len(questions), count)

        # Verify semantic type diversity (Req 7.1)
        if len(type_counts) < min_semantic_types:
            logger.warning(
                "Evaluation set covers only %d semantic types "
                "(minimum %d requested). Types: %s",
                len(type_counts),
                min_semantic_types,
                list(type_counts.keys()),
            )

        logger.info(
            "Generated evaluation set: %d questions across %d semantic types",
            len(questions),
            len(type_counts),
        )

        eval_set = EvaluationSet(
            questions=questions,
            metadata={
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "question_count": len(questions),
                "semantic_type_distribution": type_counts,
                "training_set_size": len(training_questions),
                "embedding_model": "N/A (LLM judge)",
            },
        )
        return eval_set

    # ------------------------------------------------------------------
    # Export evaluation set
    # ------------------------------------------------------------------

    @staticmethod
    def export_eval_set(eval_set: EvaluationSet, output_path: Path) -> None:
        """Export an evaluation set to JSONL (Req 7.5)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            for eq in eval_set.questions:
                line = json.dumps(
                    eq.model_dump(), ensure_ascii=False
                )
                fh.write(line + "\n")
        logger.info("Exported evaluation set to %s", output_path)

    @staticmethod
    def load_eval_set(input_path: Path) -> EvaluationSet:
        """Load an evaluation set from JSONL."""
        questions: List[EvaluationQuestion] = []
        with open(input_path, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    questions.append(EvaluationQuestion.model_validate(data))
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid eval line %d: %s", lineno, exc
                    )
        return EvaluationSet(
            questions=questions,
            metadata={"loaded_from": str(input_path)},
        )

    # ------------------------------------------------------------------
    # Main evaluation
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        eval_set_path: Path,
        base_model: str,
        finetuned_model: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> ComparisonReport:
        """Run before/after evaluation and produce a comparison report.

        Sends each evaluation question to both the base and fine-tuned
        models via Ollama, judges responses via the LLM judge, and
        aggregates results.

        Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
        """
        eval_set = self.load_eval_set(eval_set_path)
        total = len(eval_set.questions)
        if total == 0:
            raise ValueError(
                f"Evaluation set at {eval_set_path} contains no questions."
            )

        if self._judge is None:
            raise RuntimeError(
                "EvaluationRunner requires a JudgeService for evaluation. "
                "Pass judge=JudgeService(...) when constructing the runner."
            )

        logger.info(
            "Starting evaluation: %d questions, base=%s, finetuned=%s",
            total,
            base_model,
            finetuned_model,
        )

        results: List[QuestionResult] = []
        judge_success = 0
        judge_failure = 0

        for idx, eq in enumerate(eval_set.questions):
            # Query both models (Req 8.1).
            # Build the user message via the shared training helper so
            # evaluation prompts are byte-equal to training prompts for
            # the same (instruction, context) pair (clause 3.5, 3.6).
            user_message = build_inference_user_message(
                eq.question, eq.context or ""
            )

            try:
                base_response = _query_ollama(
                    base_model,
                    user_message=user_message,
                    system_prompt=_SYSTEM_PROMPT,
                )
            except RuntimeError as exc:
                logger.warning(
                    "Base model query failed for Q%d, skipping: %s",
                    idx + 1, exc,
                )
                continue

            try:
                ft_response = _query_ollama(
                    finetuned_model,
                    user_message=user_message,
                    system_prompt=_SYSTEM_PROMPT,
                )
            except RuntimeError as exc:
                logger.warning(
                    "Fine-tuned model query failed for Q%d, skipping: %s",
                    idx + 1, exc,
                )
                continue

            # Judge the response pair via LLM judge
            try:
                judge_result = await self._judge.judge_pair(
                    question=eq.question,
                    gold_answer=eq.gold_answer,
                    base_response=base_response,
                    finetuned_response=ft_response,
                )
                judge_success += 1
            except JudgeParseError as exc:
                logger.warning(
                    "Judge failed for Q%d after retries, skipping: %s",
                    idx + 1, exc,
                )
                judge_failure += 1
                continue

            # Map JudgeResult scores to ResponseScore dataclasses
            b_scores = judge_result.base_scores
            f_scores = judge_result.finetuned_scores
            base_score = ResponseScore(
                factual_accuracy=b_scores.factual_accuracy,
                completeness=b_scores.completeness,
                clinical_relevance=b_scores.clinical_relevance,
                coherence=b_scores.coherence,
            )
            ft_score = ResponseScore(
                factual_accuracy=f_scores.factual_accuracy,
                completeness=f_scores.completeness,
                clinical_relevance=f_scores.clinical_relevance,
                coherence=f_scores.coherence,
            )

            results.append(
                QuestionResult(
                    question=eq.question,
                    gold_answer=eq.gold_answer,
                    base_response=base_response,
                    finetuned_response=ft_response,
                    base_score=base_score,
                    finetuned_score=ft_score,
                    semantic_type=eq.semantic_type,
                    difficulty_level=eq.difficulty_level,
                    winner=judge_result.winner,
                    judge_explanation=judge_result.explanation,
                    position_label=judge_result.position_label,
                )
            )

            if progress_callback is not None:
                progress_callback(idx + 1, total)

        logger.info(
            "Judge calls complete: %d successful, %d failed out of %d total",
            judge_success,
            judge_failure,
            total,
        )

        # Compute similarity scores (embedding cosine sim vs gold)
        embedding_model = _load_embedding_model(
            self._config.embedding_model
        )
        if embedding_model is not None and results:
            logger.info(
                "Computing similarity scores with model '%s'...",
                self._config.embedding_model,
            )
            gold_answers = [r.gold_answer for r in results]
            base_responses = [r.base_response for r in results]
            ft_responses = [r.finetuned_response for r in results]

            base_sims = _compute_similarity(
                embedding_model, base_responses, gold_answers
            )
            ft_sims = _compute_similarity(
                embedding_model, ft_responses, gold_answers
            )

            for i, r in enumerate(results):
                r.base_similarity = round(base_sims[i], 4)
                r.finetuned_similarity = round(ft_sims[i], 4)

            logger.info("Similarity scoring complete.")

        # Aggregate scores (Req 8.4)
        report = self._build_report(
            results,
            total_questions=total,
            judge_success=judge_success,
            judge_failure=judge_failure,
        )

        # Export report (Req 8.5)
        output_dir = Path(self._config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._export_json_report(report, output_dir / "comparison_report.json")
        self._export_markdown_report(
            report, output_dir / "comparison_report.md"
        )

        return report

    # ------------------------------------------------------------------
    # Report building
    # ------------------------------------------------------------------

    def _build_report(
        self,
        results: List[QuestionResult],
        total_questions: int = 0,
        judge_success: int = 0,
        judge_failure: int = 0,
    ) -> ComparisonReport:
        """Aggregate per-question results into a ComparisonReport.

        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.1, 6.2, 6.3, 10.4
        """
        judge_stats: Dict[str, Any] = {
            "total_questions": total_questions,
            "successful_judgments": judge_success,
            "failed_judgments": judge_failure,
            "judge_model": "deepseek",
        }

        if not results:
            return ComparisonReport(
                results=[],
                win_rate=0.0,
                mean_score_delta=0.0,
                improvement_delta=0.0,
                by_semantic_type={},
                by_difficulty={},
                flagged=True,
                recommendations=["No evaluation results to analyse."],
                judge_stats=judge_stats,
            )

        # Compute mean dimension scores for each model
        dimensions = [
            "factual_accuracy",
            "completeness",
            "clinical_relevance",
            "coherence",
        ]

        def _mean_dim(
            scores_list: List[ResponseScore], dim: str
        ) -> float:
            values: List[int] = [
                getattr(s, dim) for s in scores_list
            ]
            return sum(values) / len(values)

        base_scores_list = [r.base_score for r in results]
        ft_scores_list = [r.finetuned_score for r in results]

        base_means = {
            d: round(_mean_dim(base_scores_list, d), 4)
            for d in dimensions
        }
        ft_means = {
            d: round(_mean_dim(ft_scores_list, d), 4)
            for d in dimensions
        }

        # Mean score delta: average of (ft - base) across all
        # dimensions and questions
        all_deltas: List[float] = []
        for r in results:
            for d in dimensions:
                all_deltas.append(
                    float(
                        getattr(r.finetuned_score, d)
                        - getattr(r.base_score, d)
                    )
                )
        mean_score_delta = (
            sum(all_deltas) / len(all_deltas)
            if all_deltas
            else 0.0
        )

        # Win rate: fraction of questions where finetuned wins
        win_count = sum(1 for r in results if r.winner == "finetuned")
        win_rate = win_count / len(results)

        # Improvement delta derived from win rate
        delta = win_rate - 0.5

        # Helper to compute breakdown for a group of results
        def _compute_breakdown(
            group: List[QuestionResult],
        ) -> Dict[str, Any]:
            g_win = (
                sum(1 for r in group if r.winner == "finetuned")
                / len(group)
            )
            g_deltas: List[float] = []
            for r in group:
                for d in dimensions:
                    g_deltas.append(
                        float(
                            getattr(r.finetuned_score, d)
                            - getattr(r.base_score, d)
                        )
                    )
            g_base_means = {
                d: round(
                    _mean_dim(
                        [r.base_score for r in group], d
                    ),
                    4,
                )
                for d in dimensions
            }
            g_ft_means = {
                d: round(
                    _mean_dim(
                        [r.finetuned_score for r in group],
                        d,
                    ),
                    4,
                )
                for d in dimensions
            }
            return {
                "win_rate": round(g_win, 4),
                "mean_score_delta": round(
                    sum(g_deltas) / len(g_deltas) if g_deltas else 0.0, 4
                ),
                "base_mean_scores": g_base_means,
                "finetuned_mean_scores": g_ft_means,
                "count": float(len(group)),
            }

        # Breakdown by semantic type
        by_type: Dict[str, Dict[str, Any]] = {}
        type_groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            type_groups.setdefault(r.semantic_type, []).append(r)
        for stype, group in type_groups.items():
            by_type[stype] = _compute_breakdown(group)

        # Breakdown by difficulty
        by_diff: Dict[str, Dict[str, Any]] = {}
        diff_groups: Dict[str, List[QuestionResult]] = {}
        for r in results:
            diff_groups.setdefault(r.difficulty_level, []).append(r)
        for dlevel, group in diff_groups.items():
            by_diff[dlevel] = _compute_breakdown(group)

        # Flagging (Req 6.2, 10.4)
        threshold = self._config.improvement_threshold
        high_failure_rate = (
            total_questions > 0
            and judge_failure > total_questions * 0.5
        )
        flagged = delta < threshold or high_failure_rate
        recommendations: List[str] = []

        if delta < threshold:
            recommendations.append(
                f"Improvement delta ({delta:.4f}) is below the "
                f"{threshold:.0%} threshold. Consider reviewing "
                f"training data quality and coverage."
            )
            if delta < 0:
                recommendations.append(
                    "The fine-tuned model scored lower than the base model. "
                    "This may indicate overfitting, data quality issues, or "
                    "insufficient training data."
                )
            recommendations.append(
                "Try increasing the training dataset size, improving "
                "deduplication thresholds, or adjusting hyperparameters "
                "(learning rate, epochs)."
            )

        if high_failure_rate:
            recommendations.append(
                f"High judge failure rate: {judge_failure}/{total_questions} "
                f"({judge_failure / total_questions:.0%}) of judge calls "
                f"failed. Results may not be representative. Check DeepSeek "
                f"API availability and response format."
            )

        # Aggregate similarity scores
        base_mean_sim = 0.0
        ft_mean_sim = 0.0
        sim_delta = 0.0
        sim_by_type: Dict[str, Dict[str, float]] = {}

        if results and results[0].base_similarity != 0.0:
            base_sims = [r.base_similarity for r in results]
            ft_sims = [r.finetuned_similarity for r in results]
            base_mean_sim = round(
                sum(base_sims) / len(base_sims), 4
            )
            ft_mean_sim = round(
                sum(ft_sims) / len(ft_sims), 4
            )
            sim_delta = round(ft_mean_sim - base_mean_sim, 4)

            # Per-type similarity breakdown
            for stype, group in type_groups.items():
                g_base = [r.base_similarity for r in group]
                g_ft = [r.finetuned_similarity for r in group]
                g_base_mean = round(
                    sum(g_base) / len(g_base), 4
                )
                g_ft_mean = round(
                    sum(g_ft) / len(g_ft), 4
                )
                sim_by_type[stype] = {
                    "base_mean_sim": g_base_mean,
                    "finetuned_mean_sim": g_ft_mean,
                    "delta": round(g_ft_mean - g_base_mean, 4),
                }

        return ComparisonReport(
            results=results,
            win_rate=round(win_rate, 4),
            mean_score_delta=round(mean_score_delta, 4),
            improvement_delta=round(delta, 4),
            by_semantic_type=by_type,
            by_difficulty=by_diff,
            flagged=flagged,
            recommendations=recommendations,
            judge_stats=judge_stats,
            base_mean_scores=base_means,
            finetuned_mean_scores=ft_means,
            base_mean_similarity=base_mean_sim,
            finetuned_mean_similarity=ft_mean_sim,
            similarity_delta=sim_delta,
            similarity_by_semantic_type=sim_by_type,
        )

    # ------------------------------------------------------------------
    # Report export
    # ------------------------------------------------------------------

    @staticmethod
    def _export_json_report(
        report: ComparisonReport, output_path: Path
    ) -> None:
        """Export comparison report as JSON (Req 7.1, 7.2, 7.3, 7.4, 7.5)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def _score_dict(s: ResponseScore) -> Dict[str, int]:
            return {
                "factual_accuracy": s.factual_accuracy,
                "completeness": s.completeness,
                "clinical_relevance": s.clinical_relevance,
                "coherence": s.coherence,
            }

        data: Dict[str, Any] = {
            "win_rate": report.win_rate,
            "mean_score_delta": report.mean_score_delta,
            "improvement_delta": report.improvement_delta,
            "base_mean_similarity": report.base_mean_similarity,
            "finetuned_mean_similarity": report.finetuned_mean_similarity,
            "similarity_delta": report.similarity_delta,
            "flagged": report.flagged,
            "recommendations": report.recommendations,
            "by_semantic_type": report.by_semantic_type,
            "similarity_by_semantic_type": report.similarity_by_semantic_type,
            "by_difficulty": report.by_difficulty,
            "judge_stats": report.judge_stats,
            "results": [
                {
                    "question": r.question,
                    "gold_answer": r.gold_answer,
                    "base_response": r.base_response,
                    "finetuned_response": r.finetuned_response,
                    "base_score": _score_dict(r.base_score),
                    "finetuned_score": _score_dict(r.finetuned_score),
                    "base_similarity": r.base_similarity,
                    "finetuned_similarity": r.finetuned_similarity,
                    "semantic_type": r.semantic_type,
                    "difficulty_level": r.difficulty_level,
                    "winner": r.winner,
                    "judge_explanation": r.judge_explanation,
                    "position_label": r.position_label,
                }
                for r in report.results
            ],
        }

        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        logger.info("Exported JSON report to %s", output_path)

    @staticmethod
    def _export_markdown_report(
        report: ComparisonReport, output_path: Path
    ) -> None:
        """Export comparison report as Markdown (Req 8.1–8.5)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = []
        lines.append("# Model Evaluation Report\n")
        lines.append(
            f"Generated: {datetime.now(timezone.utc).isoformat()}\n"
        )

        # Summary table (Req 8.2)
        lines.append("## Summary\n")
        lines.append(
            f"| Metric | Value |\n"
            f"|--------|-------|\n"
            f"| Win Rate "
            f"| {report.win_rate:.4f} |\n"
            f"| Mean Score Delta "
            f"| {report.mean_score_delta:.4f} |\n"
            f"| Improvement Delta "
            f"| {report.improvement_delta:.4f} |\n"
            f"| Base Mean Sim "
            f"| {report.base_mean_similarity:.4f} |\n"
            f"| Fine-tuned Mean Sim "
            f"| {report.finetuned_mean_similarity:.4f} |\n"
            f"| Similarity Delta "
            f"| {report.similarity_delta:+.4f} |\n"
            f"| Flagged "
            f"| {'Yes' if report.flagged else 'No'} |\n"
            f"| Total Questions "
            f"| {len(report.results)} |\n"
        )

        # Recommendations
        if report.recommendations:
            lines.append("## Recommendations\n")
            for rec in report.recommendations:
                lines.append(f"- {rec}\n")
            lines.append("")

        # Per-dimension breakdown table (Req 8.3)
        dimensions = [
            "factual_accuracy", "completeness",
            "clinical_relevance", "coherence",
        ]
        if report.base_mean_scores and report.finetuned_mean_scores:
            lines.append("## Per-Dimension Breakdown\n")
            lines.append(
                "| Dimension | Base Mean | Fine-tuned Mean | Delta |\n"
                "|-----------|-----------|-----------------|-------|\n"
            )
            for dim in dimensions:
                base_val = report.base_mean_scores.get(dim, 0.0)
                ft_val = report.finetuned_mean_scores.get(dim, 0.0)
                dim_delta = ft_val - base_val
                dim_label = dim.replace("_", " ").title()
                lines.append(
                    f"| {dim_label} "
                    f"| {base_val:.4f} "
                    f"| {ft_val:.4f} "
                    f"| {dim_delta:.4f} |\n"
                )
            lines.append("")

        # By semantic type (Req 8.4)
        if report.by_semantic_type:
            lines.append("## Results by Semantic Type\n")
            lines.append(
                "| Semantic Type | Count | Win Rate | Score Delta |\n"
                "|---------------|-------|----------|-------------|\n"
            )
            for stype, metrics in sorted(report.by_semantic_type.items()):
                lines.append(
                    f"| {stype} "
                    f"| {int(metrics.get('count', 0))} "
                    f"| {metrics.get('win_rate', 0):.4f} "
                    f"| {metrics.get('mean_score_delta', 0):.4f} |\n"
                )
            lines.append("")

        # Similarity by semantic type
        if report.similarity_by_semantic_type:
            lines.append("## Similarity by Semantic Type\n")
            lines.append(
                "| Semantic Type | Base Sim | FT Sim | Delta |\n"
                "|---------------|----------|--------|-------|\n"
            )
            for stype, metrics in sorted(
                report.similarity_by_semantic_type.items()
            ):
                lines.append(
                    f"| {stype} "
                    f"| {metrics.get('base_mean_sim', 0):.4f} "
                    f"| {metrics.get('finetuned_mean_sim', 0):.4f} "
                    f"| {metrics.get('delta', 0):+.4f} |\n"
                )
            lines.append("")

        # By difficulty (Req 8.5)
        if report.by_difficulty:
            lines.append("## Results by Difficulty\n")
            lines.append(
                "| Difficulty | Count | Win Rate | Score Delta |\n"
                "|------------|-------|----------|-------------|\n"
            )
            for dlevel, metrics in sorted(report.by_difficulty.items()):
                lines.append(
                    f"| {dlevel} "
                    f"| {int(metrics.get('count', 0))} "
                    f"| {metrics.get('win_rate', 0):.4f} "
                    f"| {metrics.get('mean_score_delta', 0):.4f} |\n"
                )
            lines.append("")

        # Per-question results
        if report.results:
            lines.append("## Per-Question Results\n")
            lines.append(
                "| # | Question | Semantic Type | Difficulty "
                "| Winner | Base Avg | FT Avg |\n"
                "|---|----------|---------------|------------"
                "|--------|----------|--------|\n"
            )
            for i, r in enumerate(report.results, start=1):
                q_short = (
                    r.question[:60] + "..."
                    if len(r.question) > 60
                    else r.question
                )
                dims = [
                    "factual_accuracy",
                    "completeness",
                    "clinical_relevance",
                    "coherence",
                ]
                base_vals = [getattr(r.base_score, d) for d in dims]
                ft_vals = [getattr(r.finetuned_score, d) for d in dims]
                base_avg = sum(base_vals) / len(base_vals)
                ft_avg = sum(ft_vals) / len(ft_vals)
                lines.append(
                    f"| {i} | {q_short} | {r.semantic_type} "
                    f"| {r.difficulty_level} "
                    f"| {r.winner} "
                    f"| {base_avg:.2f} "
                    f"| {ft_avg:.2f} |\n"
                )

        with open(output_path, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        logger.info("Exported Markdown report to %s", output_path)
