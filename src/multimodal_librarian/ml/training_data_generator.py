"""
Training Data Generator orchestrator.

Orchestrates Q&A pair generation from all three strategies (KG, RAG,
UMLS Reasoning), handles deduplication, quality validation, and JSONL
export. Runs as a Celery task inside Docker with access to Neo4j,
Milvus, and the RAG pipeline.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7,
              11.1, 11.2, 11.3, 11.4, 11.5,
              12.1, 12.2, 12.3, 12.4
"""

from __future__ import annotations

import json
import logging
import random
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .models import (
    DatasetSummary,
    InstructionTuningPair,
    TrainingDataConfig,
    TrainingDataResult,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_DATASET_SIZE_WARNING = 1000
_MIN_QUALITY_PASS_RATE = 0.70
_MIN_RESPONSE_TOKENS = 50


def _count_tokens(text: str) -> int:
    """Approximate token count by splitting on whitespace."""
    return len(text.split())


# ---------------------------------------------------------------------------
# Normalised string similarity for deduplication
# ---------------------------------------------------------------------------


def _normalise_text(text: str) -> str:
    """Normalise text for similarity comparison.

    Lowercases, strips accents via NFD decomposition, collapses
    whitespace, and removes common punctuation.
    """
    text = text.lower().strip()
    # NFD decompose then drop combining characters (accents)
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    # Collapse whitespace
    text = " ".join(text.split())
    # Remove common punctuation
    text = text.replace("?", "").replace(".", "").replace(",", "")
    text = text.replace("!", "").replace(";", "").replace(":", "")
    return text


def _char_bigrams(text: str) -> Set[str]:
    """Return the set of character bigrams in *text*."""
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _normalised_similarity(a: str, b: str) -> float:
    """Compute normalised string similarity using Sørensen–Dice on bigrams.

    Returns a value in [0.0, 1.0] where 1.0 means identical after
    normalisation.
    """
    na = _normalise_text(a)
    nb = _normalise_text(b)
    if na == nb:
        return 1.0
    if not na or not nb:
        return 0.0
    bigrams_a = _char_bigrams(na)
    bigrams_b = _char_bigrams(nb)
    intersection = bigrams_a & bigrams_b
    total = len(bigrams_a) + len(bigrams_b)
    if total == 0:
        return 1.0
    return 2.0 * len(intersection) / total


# ---------------------------------------------------------------------------
# LLM adapter for DeepSeekAIService
# ---------------------------------------------------------------------------


class _DeepSeekLLMAdapter:
    """Thin adapter exposing a ``generate(prompt, system_prompt=...)`` interface.

    ``LLMQuestionRewriter`` and ``TokenBudgetManager`` expect an LLM
    client with an async ``generate(prompt, system_prompt=...)`` method.
    ``DeepSeekAIService`` only exposes ``generate_response(messages)``.
    This adapter bridges the two interfaces.
    """

    def __init__(self, ai_service: Any) -> None:
        self._ai = ai_service

    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
    ) -> str:
        """Call the underlying AI service and return the text content."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = await self._ai.generate_response(
            messages=messages,
            temperature=0.7,
            max_tokens=512,
        )
        # AIResponse has a .content attribute with the text.
        return response.content if hasattr(response, "content") else str(response)


# ---------------------------------------------------------------------------
# TrainingDataGenerator
# ---------------------------------------------------------------------------


class TrainingDataGenerator:
    """Orchestrates medical Q&A training data generation.

    Runs all three generation strategies (KG, RAG, UMLS Reasoning),
    merges results, deduplicates by normalised instruction similarity,
    validates quality, and exports the final dataset as JSONL.

    Args:
        neo4j_client: A Neo4j client with an async ``execute_query``
            method.
        vector_client: A vector-store client with an async
            ``get_chunk_by_id`` method (e.g. ``MilvusClient``).
        rag_service: The existing ``RAGService`` for generating cited
            responses.
        umls_client: The ``UMLSClient`` for UMLS concept lookups.
        relationship_traverser: The ``RelationshipTraverser`` for
            discovering relationship paths between concepts.
        ner_extractor: The ``NER_Extractor`` for validating UMLS
            concept presence in responses.
    """

    def __init__(
        self,
        neo4j_client: Any,
        vector_client: Any,
        rag_service: Any,
        umls_client: Any,
        relationship_traverser: Any,
        ner_extractor: Any,
    ) -> None:
        self._neo4j = neo4j_client
        self._vector = vector_client
        self._rag = rag_service
        self._umls = umls_client
        self._traverser = relationship_traverser
        self._ner = ner_extractor

    # ------------------------------------------------------------------
    # Main generation pipeline
    # ------------------------------------------------------------------

    async def generate(
        self,
        config: TrainingDataConfig,
        progress_callback: Optional[
            Callable[[str, int, int], None]
        ] = None,
        pre_existing_pairs: Optional[
            Dict[str, List[InstructionTuningPair]]
        ] = None,
    ) -> TrainingDataResult:
        """Run all strategies, deduplicate, validate, and export.

        When *pre_existing_pairs* is provided (resume flow), each
        strategy's target is reduced by the number of pre-existing
        pairs for that strategy.  Strategies whose pre-existing count
        meets or exceeds the target are skipped entirely.  After all
        strategies run, pre-existing and newly generated pairs are
        merged, deduplicated together, and only the *new* pairs go
        through quality validation — pre-existing pairs are treated as
        already validated (Requirement 4.5).

        Args:
            config: Generation configuration.
            progress_callback: Optional ``(phase, current, total)``
                callback for reporting progress.
            pre_existing_pairs: Optional mapping of strategy name to
                previously generated pairs from a failed run.  Keys
                are ``"kg"``, ``"rag"``, or ``"umls_reasoning"``.

        Returns:
            A ``TrainingDataResult`` with dataset summary, validation
            result, and output path.
        """
        start_time = time.monotonic()
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if pre_existing_pairs is None:
            pre_existing_pairs = {}

        # Collect newly generated pairs separately from pre-existing
        # so we can apply validation only to new pairs.
        new_pairs: List[InstructionTuningPair] = []
        all_pre_existing: List[InstructionTuningPair] = []

        # Compute per-strategy budgets
        strategy_count = len(config.strategies)
        per_strategy = (
            config.target_pair_count // strategy_count
            if strategy_count > 0
            else config.target_pair_count
        )

        # --- KG Strategy ---
        if "kg" in config.strategies:
            existing_kg = pre_existing_pairs.get("kg", [])
            effective_target = max(0, per_strategy - len(existing_kg))

            if effective_target == 0:
                logger.info(
                    "Training data: KG strategy skipped — %d "
                    "pre-existing pairs meet or exceed target of %d",
                    len(existing_kg),
                    per_strategy,
                )
                all_pre_existing.extend(existing_kg)
            else:
                if existing_kg:
                    logger.info(
                        "Training data: KG strategy target reduced "
                        "from %d to %d (%d pre-existing pairs)",
                        per_strategy,
                        effective_target,
                        len(existing_kg),
                    )
                    all_pre_existing.extend(existing_kg)
                if progress_callback:
                    progress_callback(
                        "kg_generation", 0, effective_target
                    )
                kg_pairs = await self._run_kg_strategy(
                    effective_target, config, progress_callback
                )
                new_pairs.extend(kg_pairs)
                # Save incrementally so data survives task failures
                self._save_partial(
                    kg_pairs, output_dir / "partial_kg.jsonl"
                )
                logger.info(
                    "Training data: KG strategy produced %d pairs "
                    "(saved)",
                    len(kg_pairs),
                )

        # --- RAG Strategy ---
        if "rag" in config.strategies:
            existing_rag = pre_existing_pairs.get("rag", [])
            effective_target = max(0, per_strategy - len(existing_rag))

            if effective_target == 0:
                logger.info(
                    "Training data: RAG strategy skipped — %d "
                    "pre-existing pairs meet or exceed target of %d",
                    len(existing_rag),
                    per_strategy,
                )
                all_pre_existing.extend(existing_rag)
            else:
                if existing_rag:
                    logger.info(
                        "Training data: RAG strategy target reduced "
                        "from %d to %d (%d pre-existing pairs)",
                        per_strategy,
                        effective_target,
                        len(existing_rag),
                    )
                    all_pre_existing.extend(existing_rag)
                if progress_callback:
                    progress_callback(
                        "rag_generation", 0, effective_target
                    )
                rag_pairs = await self._run_rag_strategy(
                    effective_target, config, progress_callback
                )
                new_pairs.extend(rag_pairs)
                self._save_partial(
                    rag_pairs, output_dir / "partial_rag.jsonl"
                )
                logger.info(
                    "Training data: RAG strategy produced %d pairs "
                    "(saved)",
                    len(rag_pairs),
                )

        # --- UMLS Reasoning Strategy ---
        if "umls_reasoning" in config.strategies:
            existing_umls = pre_existing_pairs.get(
                "umls_reasoning", []
            )
            effective_target = max(
                0, per_strategy - len(existing_umls)
            )

            if effective_target == 0:
                logger.info(
                    "Training data: UMLS Reasoning strategy skipped "
                    "— %d pre-existing pairs meet or exceed target "
                    "of %d",
                    len(existing_umls),
                    per_strategy,
                )
                all_pre_existing.extend(existing_umls)
            else:
                if existing_umls:
                    logger.info(
                        "Training data: UMLS Reasoning strategy "
                        "target reduced from %d to %d (%d "
                        "pre-existing pairs)",
                        per_strategy,
                        effective_target,
                        len(existing_umls),
                    )
                    all_pre_existing.extend(existing_umls)
                if progress_callback:
                    progress_callback(
                        "umls_generation", 0, effective_target
                    )
                umls_pairs = await self._run_umls_strategy(
                    effective_target, config, progress_callback
                )
                new_pairs.extend(umls_pairs)
                self._save_partial(
                    umls_pairs, output_dir / "partial_umls.jsonl"
                )
                logger.info(
                    "Training data: UMLS Reasoning strategy produced"
                    " %d pairs (saved)",
                    len(umls_pairs),
                )

        # --- Merge pre-existing + new pairs ---
        all_pairs = all_pre_existing + new_pairs
        logger.info(
            "Training data: Total pairs before dedup: %d "
            "(%d pre-existing + %d new)",
            len(all_pairs),
            len(all_pre_existing),
            len(new_pairs),
        )

        # --- Deduplicate across all pairs (Requirement 4.4) ---
        if progress_callback:
            progress_callback("assembly", 0, len(all_pairs))
        deduped = self.deduplicate(
            all_pairs, similarity_threshold=config.similarity_threshold
        )
        dedup_removed = len(all_pairs) - len(deduped)
        logger.info(
            "Training data: After dedup: %d pairs (%d removed)",
            len(deduped),
            dedup_removed,
        )

        # Warn if dataset is too small (Requirement 4.7)
        if len(deduped) < _MIN_DATASET_SIZE_WARNING:
            per_strategy_counts = self._count_per_strategy(deduped)
            logger.warning(
                "Training data: Dataset has only %d pairs after dedup "
                "(< %d). Per-strategy counts: %s",
                len(deduped),
                _MIN_DATASET_SIZE_WARNING,
                per_strategy_counts,
            )

        # --- Validate (Requirement 4.5) ---
        # Pre-existing pairs bypass validation; only new pairs are
        # validated.  Build a set of pre-existing pair identities so
        # we can partition the deduped list.
        pre_existing_ids: set = {
            id(p) for p in all_pre_existing
        }
        deduped_pre_existing = [
            p for p in deduped if id(p) in pre_existing_ids
        ]
        deduped_new = [
            p for p in deduped if id(p) not in pre_existing_ids
        ]

        validation = await self.validate_dataset(deduped_new)
        logger.info(
            "Training data: Validation (new pairs only) — "
            "%d accepted, %d rejected (pass rate: %.1f%%)",
            len(validation.accepted),
            len(validation.rejected),
            validation.pass_rate * 100,
        )

        # Combine: all surviving pre-existing + validated new pairs
        final_accepted = deduped_pre_existing + validation.accepted

        if deduped_pre_existing:
            logger.info(
                "Training data: %d pre-existing pairs included "
                "(bypassed validation)",
                len(deduped_pre_existing),
            )

        # Warn if quality pass rate is too low (Requirement 11.5)
        if validation.pass_rate < _MIN_QUALITY_PASS_RATE:
            logger.warning(
                "Training data: Quality pass rate %.1f%% is below "
                "%.0f%% threshold. Review generation strategy "
                "parameters.",
                validation.pass_rate * 100,
                _MIN_QUALITY_PASS_RATE * 100,
            )

        # Log quality summary (Requirement 11.4)
        reason_dist = Counter(
            reason
            for reasons in validation.rejection_reasons.values()
            for reason in reasons
        )
        logger.info(
            "Training data: Quality summary — total=%d, "
            "pass_rate=%.2f, rejection_reasons=%s",
            validation.total,
            validation.pass_rate,
            dict(reason_dist),
        )

        # --- Export rejected pairs ---
        if validation.rejected:
            rejected_path = output_dir / "rejected_pairs.jsonl"
            self.print_jsonl(validation.rejected, rejected_path)
            logger.info(
                "Training data: Rejected pairs written to %s",
                rejected_path,
            )

        # --- Export accepted pairs (pre-existing + validated new) ---
        output_path = output_dir / "training_data.jsonl"
        summary = self.export_jsonl(
            final_accepted, output_path, seed=config.random_seed
        )
        summary.dedup_removed = dedup_removed

        elapsed = time.monotonic() - start_time
        result = TrainingDataResult(
            dataset_summary=summary,
            validation_result=validation,
            output_path=str(output_path),
            generation_time_seconds=round(elapsed, 2),
        )

        logger.info(
            "Training data: Generation complete in %.1fs — "
            "%d pairs exported to %s",
            elapsed,
            summary.total_pairs,
            output_path,
        )
        return result

    # ------------------------------------------------------------------
    # Incremental save
    # ------------------------------------------------------------------

    @staticmethod
    def _save_partial(
        pairs: List[InstructionTuningPair],
        path: Path,
    ) -> None:
        """Save pairs to a JSONL file so data survives task failures."""
        try:
            with path.open("w", encoding="utf-8") as fh:
                for pair in pairs:
                    fh.write(pair.to_jsonl_line() + "\n")
            logger.info(
                "Training data: Saved %d partial pairs to %s",
                len(pairs),
                path,
            )
        except Exception as exc:
            logger.warning(
                "Training data: Failed to save partial pairs to %s: %s",
                path,
                exc,
            )

    # ------------------------------------------------------------------
    # Strategy runners
    # ------------------------------------------------------------------

    async def _run_kg_strategy(
        self,
        target_count: int,
        config: TrainingDataConfig,
        progress_callback: Optional[Callable] = None,
    ) -> List[InstructionTuningPair]:
        """Run the KG Q&A strategy."""
        from .kg_qa_strategy import KGQAStrategy

        strategy = KGQAStrategy(
            neo4j_client=self._neo4j,
            vector_client=self._vector,
        )

        def _kg_progress(current: int, total: int) -> None:
            if progress_callback:
                progress_callback("kg_generation", current, total)

        try:
            return await strategy.generate(
                target_count=target_count,
                min_chunk_tokens=config.min_chunk_tokens,
                progress_callback=_kg_progress,
            )
        except Exception as exc:
            logger.error(
                "Training data: KG strategy failed — skipping: %s", exc
            )
            return []

    async def _run_rag_strategy(
        self,
        target_count: int,
        config: TrainingDataConfig,
        progress_callback: Optional[Callable] = None,
    ) -> List[InstructionTuningPair]:
        """Run the RAG Q&A strategy with incremental saving."""
        from .quality_filter import QualityFilter
        from .question_rewriter import LLMQuestionRewriter
        from .rag_qa_strategy import RAGQAStrategy
        from .token_budget import TokenBudgetManager

        # Build an LLM adapter that exposes the simple
        # generate(prompt, system_prompt=...) interface expected by
        # LLMQuestionRewriter and TokenBudgetManager from the
        # DeepSeekAIService (which only has generate_response(messages)).
        llm_adapter = None
        if self._rag is not None and hasattr(self._rag, "ai_service"):
            ai_service = self._rag.ai_service
            if ai_service is not None:
                llm_adapter = _DeepSeekLLMAdapter(ai_service)

        # Instantiate conversational training data components.
        question_rewriter = None
        if llm_adapter is not None:
            question_rewriter = LLMQuestionRewriter(
                llm_client=llm_adapter, max_concurrent=4
            )

        quality_filter = QualityFilter()

        token_budget_manager = TokenBudgetManager(
            max_tokens=5000,
            llm_client=llm_adapter,
        )

        strategy = RAGQAStrategy(
            rag_service=self._rag,
            neo4j_client=self._neo4j,
            umls_client=self._umls,
            question_rewriter=question_rewriter,
            quality_filter=quality_filter,
            token_budget_manager=token_budget_manager,
        )

        output_dir = Path(config.output_dir)
        partial_path = output_dir / "partial_rag.jsonl"
        partial_path.parent.mkdir(parents=True, exist_ok=True)

        # Provide a rewriting progress callback so the Celery task
        # can report the rewriting phase separately.
        def _rewrite_progress(current: int, total: int) -> None:
            if progress_callback:
                progress_callback("rag_rewriting", current, total)

        def _rag_progress(current: int, total: int) -> None:
            if progress_callback:
                progress_callback("rag_generation", current, total)

        try:
            result = await strategy.generate(
                target_count=target_count,
                semantic_types=config.semantic_types,
                progress_callback=_rag_progress,
                rewrite_progress_callback=_rewrite_progress,
                partial_save_path=partial_path,
            )

            # Distill responses: rewrite RAG-grounded responses into
            # standalone authoritative prose for knowledge distillation.
            if llm_adapter is not None and result:
                from .response_distiller import ResponseDistiller

                distiller = ResponseDistiller(
                    llm_client=llm_adapter, max_concurrent=4
                )

                def _distill_progress(current: int, total: int) -> None:
                    if progress_callback:
                        progress_callback("rag_distilling", current, total)

                batch = [
                    {"question": p.instruction, "response": p.response}
                    for p in result
                ]
                distilled = await distiller.distill_batch(
                    batch, progress_callback=_distill_progress
                )

                # Update pairs with distilled responses
                for pair, d in zip(result, distilled):
                    pair.response = d["response"]

                logger.info(
                    "Training data: Distilled %d/%d responses "
                    "(%d failed, kept original)",
                    distiller.success_count,
                    len(result),
                    distiller.failure_count,
                )

            return result
        except Exception as exc:
            logger.error(
                "Training data: RAG strategy failed — skipping: %s", exc
            )
            # Try to recover whatever was saved incrementally
            recovered = []
            if partial_path.exists():
                try:
                    recovered = self.parse_jsonl(partial_path)
                    logger.info(
                        "Training data: Recovered %d RAG pairs from "
                        "partial save",
                        len(recovered),
                    )
                except Exception:
                    pass
            return recovered

    async def _run_umls_strategy(
        self,
        target_count: int,
        config: TrainingDataConfig,
        progress_callback: Optional[Callable] = None,
    ) -> List[InstructionTuningPair]:
        """Run the UMLS Reasoning strategy."""
        from .umls_reasoning_strategy import UMLSReasoningStrategy

        strategy = UMLSReasoningStrategy(
            relationship_traverser=self._traverser,
            umls_client=self._umls,
            vector_client=self._vector,
        )

        def _umls_progress(current: int, total: int) -> None:
            if progress_callback:
                progress_callback("umls_generation", current, total)

        try:
            return await strategy.generate(
                target_count=target_count,
                progress_callback=_umls_progress,
            )
        except Exception as exc:
            logger.error(
                "Training data: UMLS Reasoning strategy failed — "
                "skipping: %s",
                exc,
            )
            return []

    # ------------------------------------------------------------------
    # Deduplication (Requirement 4.2)
    # ------------------------------------------------------------------

    def deduplicate(
        self,
        pairs: List[InstructionTuningPair],
        similarity_threshold: float = 0.85,
    ) -> List[InstructionTuningPair]:
        """Remove near-duplicate pairs by normalised instruction similarity.

        Uses Sørensen–Dice coefficient on character bigrams of the
        normalised instruction text. A pair is removed if its
        instruction has similarity >= *similarity_threshold* with any
        already-accepted pair.

        Args:
            pairs: Input list of instruction-tuning pairs.
            similarity_threshold: Similarity threshold in [0.0, 1.0].
                Pairs with similarity >= this value are considered
                duplicates. Default is 0.85.

        Returns:
            A deduplicated list preserving insertion order.
        """
        if not pairs:
            return []

        accepted: List[InstructionTuningPair] = []
        accepted_normalised: List[str] = []
        accepted_bigrams: List[Set[str]] = []

        for pair in pairs:
            norm = _normalise_text(pair.instruction)
            bigrams = _char_bigrams(norm)
            is_dup = False

            for i, existing_norm in enumerate(accepted_normalised):
                # Fast exact-match check
                if norm == existing_norm:
                    is_dup = True
                    break
                # Bigram similarity
                existing_bigrams = accepted_bigrams[i]
                intersection = bigrams & existing_bigrams
                total = len(bigrams) + len(existing_bigrams)
                if total == 0:
                    sim = 1.0
                else:
                    sim = 2.0 * len(intersection) / total
                if sim >= similarity_threshold:
                    is_dup = True
                    break

            if not is_dup:
                accepted.append(pair)
                accepted_normalised.append(norm)
                accepted_bigrams.append(bigrams)

        return accepted

    # ------------------------------------------------------------------
    # Dataset validation (Requirements 11.1–11.5)
    # ------------------------------------------------------------------

    async def validate_dataset(
        self,
        pairs: List[InstructionTuningPair],
    ) -> ValidationResult:
        """Quality-check pairs and partition into accepted/rejected.

        Checks performed on each pair:
        1. Non-empty instruction (Requirement 11.1)
        2. Non-empty context (Requirement 11.1)
        3. Valid JSON structure — already guaranteed by Pydantic model
        4. Minimum response length of 50 tokens (Requirement 11.1)
        5. At least one NER-recognised UMLS concept in the response
           (Requirement 11.2)

        Args:
            pairs: List of pairs to validate.

        Returns:
            A ``ValidationResult`` with accepted/rejected partitions
            and rejection reasons.
        """
        accepted: List[InstructionTuningPair] = []
        rejected: List[InstructionTuningPair] = []
        rejection_reasons: Dict[str, List[str]] = {}

        for pair in pairs:
            reasons: List[str] = []

            # Check non-empty instruction
            if not pair.instruction or not pair.instruction.strip():
                reasons.append("empty_instruction")

            # Check non-empty context
            if not pair.context or not pair.context.strip():
                reasons.append("empty_context")

            # Check minimum response length (50 tokens)
            if _count_tokens(pair.response) < _MIN_RESPONSE_TOKENS:
                reasons.append(
                    f"response_too_short "
                    f"({_count_tokens(pair.response)} tokens < "
                    f"{_MIN_RESPONSE_TOKENS})"
                )

            # Check for at least one NER-recognised UMLS concept
            if not reasons:
                # Only run NER if other checks pass (performance)
                has_concept = await self._check_umls_concept(pair.response)
                if not has_concept:
                    reasons.append("no_umls_concept_in_response")

            if reasons:
                rejected.append(pair)
                rejection_reasons[pair.instruction[:100]] = reasons
            else:
                accepted.append(pair)

        total = len(accepted) + len(rejected)
        pass_rate = len(accepted) / total if total > 0 else 0.0

        return ValidationResult(
            accepted=accepted,
            rejected=rejected,
            rejection_reasons=rejection_reasons,
            total=total,
            pass_rate=pass_rate,
        )

    async def _check_umls_concept(self, text: str) -> bool:
        """Check whether *text* contains at least one UMLS concept.

        Uses the NER_Extractor's ``extract_key_terms`` method. If the
        extractor is unavailable or fails, returns ``True`` to avoid
        rejecting pairs due to infrastructure issues.
        """
        if self._ner is None:
            return True
        try:
            result = await self._ner.extract_key_terms(text)
            # NERResult has umls_entities and key_terms
            umls_entities = getattr(result, "umls_entities", None)
            if umls_entities:
                return True
            # Fall back to key_terms if umls_entities is empty
            key_terms = getattr(result, "key_terms", None)
            if key_terms:
                return True
            return False
        except Exception as exc:
            logger.warning(
                "Training data: NER extraction failed — "
                "accepting pair by default: %s",
                exc,
            )
            return True

    # ------------------------------------------------------------------
    # JSONL export (Requirements 4.3, 4.4, 4.5, 12.1, 12.2)
    # ------------------------------------------------------------------

    def export_jsonl(
        self,
        pairs: List[InstructionTuningPair],
        output_path: Path,
        seed: int = 42,
    ) -> DatasetSummary:
        """Shuffle and write pairs to JSONL with metadata.

        Shuffles the pairs using a configurable random seed for
        reproducibility (Requirement 4.3), writes each pair as a
        single JSON line (Requirement 4.4), and produces a dataset
        summary (Requirement 4.5).

        Args:
            pairs: Validated pairs to export.
            output_path: Path to the output JSONL file.
            seed: Random seed for deterministic shuffling.

        Returns:
            A ``DatasetSummary`` with statistics about the exported
            dataset.
        """
        # Deterministic shuffle (Requirement 4.3)
        shuffled = list(pairs)
        rng = random.Random(seed)
        rng.shuffle(shuffled)

        # Write JSONL
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.print_jsonl(shuffled, output_path)

        # Compute summary statistics
        summary = self._compute_summary(shuffled, str(output_path))
        return summary

    # ------------------------------------------------------------------
    # JSONL parse / print (Requirements 12.1–12.4)
    # ------------------------------------------------------------------

    @staticmethod
    def parse_jsonl(
        input_path: Path,
    ) -> List[InstructionTuningPair]:
        """Parse a JSONL file into InstructionTuningPair objects.

        Invalid lines (malformed JSON or missing required fields) are
        skipped with a log entry containing the line number
        (Requirement 12.4).

        Args:
            input_path: Path to the JSONL file.

        Returns:
            A list of successfully parsed ``InstructionTuningPair``
            objects.
        """
        pairs: List[InstructionTuningPair] = []
        input_path = Path(input_path)

        with input_path.open("r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    pair = InstructionTuningPair.from_jsonl_line(line)
                    pairs.append(pair)
                except (json.JSONDecodeError, Exception) as exc:
                    logger.warning(
                        "Training data: Skipping invalid JSONL line %d: %s",
                        line_num,
                        exc,
                    )

        return pairs

    @staticmethod
    def print_jsonl(
        pairs: List[InstructionTuningPair],
        output_path: Path,
    ) -> None:
        """Serialize InstructionTuningPair objects to JSONL.

        Each object is written as a single JSON line with consistent
        field ordering (instruction, context, response, metadata) and
        UTF-8 encoding (Requirements 12.1, 12.2).

        Args:
            pairs: Pairs to serialize.
            output_path: Path to the output JSONL file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as fh:
            for pair in pairs:
                fh.write(pair.to_jsonl_line() + "\n")

    # ------------------------------------------------------------------
    # Summary computation (Requirement 4.5)
    # ------------------------------------------------------------------

    def _compute_summary(
        self,
        pairs: List[InstructionTuningPair],
        output_path: str,
    ) -> DatasetSummary:
        """Compute dataset summary statistics.

        Includes: total pairs per strategy, average response length,
        concept coverage, and confidence score distribution.
        """
        if not pairs:
            return DatasetSummary(output_path=output_path)

        # Pairs per strategy
        strategy_counts: Dict[str, int] = Counter(
            p.metadata.strategy for p in pairs
        )

        # Average response length (in tokens)
        total_tokens = sum(_count_tokens(p.response) for p in pairs)
        avg_response_length = total_tokens / len(pairs)

        # Concept coverage: count of unique concepts per strategy
        concept_coverage: Dict[str, int] = {}
        all_concepts: Set[str] = set()
        for pair in pairs:
            for concept in pair.metadata.source_concepts:
                all_concepts.add(concept)
        concept_coverage["total_unique_concepts"] = len(all_concepts)

        # Per-strategy concept counts
        for strategy in strategy_counts:
            strategy_concepts: Set[str] = set()
            for pair in pairs:
                if pair.metadata.strategy == strategy:
                    for c in pair.metadata.source_concepts:
                        strategy_concepts.add(c)
            concept_coverage[f"{strategy}_concepts"] = len(strategy_concepts)

        # Confidence score distribution (bucketed)
        confidence_buckets: Dict[str, int] = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0,
        }
        for pair in pairs:
            score = pair.metadata.confidence_score
            if score < 0.2:
                confidence_buckets["0.0-0.2"] += 1
            elif score < 0.4:
                confidence_buckets["0.2-0.4"] += 1
            elif score < 0.6:
                confidence_buckets["0.4-0.6"] += 1
            elif score < 0.8:
                confidence_buckets["0.6-0.8"] += 1
            else:
                confidence_buckets["0.8-1.0"] += 1

        return DatasetSummary(
            total_pairs=len(pairs),
            pairs_per_strategy=dict(strategy_counts),
            avg_response_length=round(avg_response_length, 1),
            concept_coverage=concept_coverage,
            confidence_distribution=confidence_buckets,
            output_path=output_path,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _count_per_strategy(
        pairs: List[InstructionTuningPair],
    ) -> Dict[str, int]:
        """Count pairs per strategy for diagnostic logging."""
        return dict(Counter(p.metadata.strategy for p in pairs))
