"""
Celery tasks for ML training data generation.

Provides an async Celery task that instantiates TrainingDataGenerator
with existing service dependencies and orchestrates Q&A pair generation
from the knowledge graph, RAG pipeline, and UMLS relationships.

Progress is reported via Celery task state updates and persisted in Redis
for resilience against hard timeouts.

Requirements: 9.1, 9.3
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import redis

from .celery_service import CELERY_BROKER_URL, celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Redis keys for ML training progress persistence
# ---------------------------------------------------------------------------

_ML_PROGRESS_PREFIX = "ml_training_progress"
_ML_PROGRESS_TTL = 24 * 60 * 60  # 24 hours

_progress_redis: Optional[redis.Redis] = None


def _get_progress_redis() -> redis.Redis:
    """Lazily initialise a Redis client for progress persistence."""
    global _progress_redis
    if _progress_redis is None:
        _progress_redis = redis.Redis.from_url(
            CELERY_BROKER_URL, decode_responses=True
        )
    return _progress_redis


def _progress_key(job_id: str) -> str:
    return f"{_ML_PROGRESS_PREFIX}:{job_id}"


def _persist_progress(job_id: str, progress: Dict[str, Any]) -> None:
    """Persist progress snapshot to Redis for hard-timeout recovery."""
    try:
        r = _get_progress_redis()
        r.setex(
            _progress_key(job_id),
            _ML_PROGRESS_TTL,
            json.dumps(progress),
        )
    except Exception as exc:
        logger.warning(
            "ML training: failed to persist progress to Redis: %s", exc
        )


def get_persisted_progress(job_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve the last persisted progress snapshot from Redis.

    Returns None if no snapshot exists or Redis is unreachable.
    """
    try:
        r = _get_progress_redis()
        raw = r.get(_progress_key(job_id))
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning(
            "ML training: failed to read progress from Redis: %s", exc
        )
    return None


def cleanup_progress(job_id: str) -> None:
    """Remove persisted progress after job completion."""
    try:
        r = _get_progress_redis()
        r.delete(_progress_key(job_id))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Service dependency helpers (run inside the Celery worker)
# ---------------------------------------------------------------------------


async def _build_training_data_generator(strategies: Optional[List[str]] = None) -> Any:
    """Instantiate TrainingDataGenerator with live service dependencies.

    This runs inside the Celery worker process which has access to
    Neo4j, Milvus, and the RAG pipeline via Docker networking.

    Must be called from within an async context (e.g. ``asyncio.run``).

    Args:
        strategies: List of active strategies. When ``"rag"`` is
            included, the full RAG service (with AI service) is
            constructed. Otherwise ``rag_service`` is ``None``.
    """
    from ..components.kg_retrieval.ner_extractor import NER_Extractor
    from ..components.kg_retrieval.relationship_traverser import RelationshipTraverser
    from ..components.knowledge_graph.umls_client import UMLSClient
    from ..ml.training_data_generator import TrainingDataGenerator

    # --- Neo4j client ---
    neo4j_uri = os.environ.get("NEO4J_URI", "bolt://neo4j:7687")
    neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
    neo4j_password = os.environ.get("NEO4J_PASSWORD", "password")

    from ..clients.neo4j_client import get_neo4j_client

    neo4j_client = get_neo4j_client(
        uri=neo4j_uri, user=neo4j_user, password=neo4j_password
    )

    # Ensure the client is connected (connect() is async)
    await neo4j_client.connect()
    logger.info("Neo4j client connected for training data generation")

    # --- Milvus / vector client ---
    from ..clients.milvus_client import MilvusClient

    milvus_host = os.environ.get("MILVUS_HOST", "milvus-standalone")
    milvus_port = int(os.environ.get("MILVUS_PORT", "19530"))
    vector_client = MilvusClient(host=milvus_host, port=milvus_port)

    # Connect Milvus client
    try:
        await vector_client.connect()
        logger.info("Milvus client connected for training data generation")
    except Exception as exc:
        logger.warning("Milvus connect failed: %s", exc)

    # --- UMLS client ---
    umls_client = UMLSClient(neo4j_client=neo4j_client)

    # --- Relationship traverser ---
    relationship_traverser = RelationshipTraverser(neo4j_client=neo4j_client)

    # --- NER extractor ---
    spacy_web_nlp = None
    spacy_sci_nlp = None
    try:
        import spacy

        spacy_web_nlp = spacy.load("en_core_web_sm")
    except Exception:
        logger.warning("en_core_web_sm unavailable for NER_Extractor")
    try:
        import spacy

        spacy_sci_nlp = spacy.load("en_core_sci_sm")
    except Exception:
        logger.warning("en_core_sci_sm unavailable for NER_Extractor")

    ner_extractor = NER_Extractor(
        spacy_web_nlp=spacy_web_nlp,
        spacy_sci_nlp=spacy_sci_nlp,
        umls_client=umls_client,
    )

    # --- RAG service (only needed if 'rag' strategy is requested) ---
    # RAG service requires ai_service which is expensive to construct.
    # Pass None when RAG strategy is not in use — TrainingDataGenerator
    # only accesses self._rag when "rag" is in config.strategies.
    #
    # For training data generation we use OllamaAIService (local
    # llama3.1:8b) instead of AIService (Gemini) to eliminate API
    # cost.  The model name is configurable via OLLAMA_TRAINING_MODEL.
    rag_service = None
    if strategies and "rag" in strategies:
        try:
            # Use DeepSeek API if key is available, otherwise fall back
            # to Ollama for local inference.
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if deepseek_key:
                from ..services.deepseek_ai_service import DeepSeekAIService
                from ..services.rag_service import RAGService

                ai_service = DeepSeekAIService()
                await ai_service.verify_available()

                rag_service = RAGService(
                    vector_client=vector_client,
                    ai_service=ai_service,
                )
                logger.info(
                    "RAG service constructed for training data generation "
                    "(DeepSeek model=%s)",
                    ai_service.model,
                )
            else:
                from ..services.ollama_ai_service import OllamaAIService
                from ..services.rag_service import RAGService

                ai_service = OllamaAIService()

                # Hard pre-flight gate: verify the Ollama training model
                # is reachable and responds BEFORE any expensive work.
                # If this fails, the entire task aborts immediately.
                await ai_service.verify_available()

                rag_service = RAGService(
                    vector_client=vector_client,
                    ai_service=ai_service,
                )
                logger.info(
                    "RAG service constructed for training data generation "
                    "(Ollama model=%s)",
                    ai_service.model,
                )
        except Exception as exc:
            logger.warning(
                "Failed to construct RAG service: %s. "
                "RAG strategy will be skipped.",
                exc,
            )

    return TrainingDataGenerator(
        neo4j_client=neo4j_client,
        vector_client=vector_client,
        rag_service=rag_service,
        umls_client=umls_client,
        relationship_traverser=relationship_traverser,
        ner_extractor=ner_extractor,
    )


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

# Route ML training tasks to a dedicated queue so they don't compete
# with document-processing tasks.
celery_app.conf.task_routes.update(
    {"generate_training_data_task": {"queue": "ml_training"}}
)


@celery_app.task(
    bind=True,
    name="generate_training_data_task",
    time_limit=40 * 60 * 60,       # 40 hours hard limit
    soft_time_limit=35 * 60 * 60,  # 35 hours soft limit
    acks_late=False,
    reject_on_worker_lost=True,
)
def generate_training_data_task(
    self,
    job_id: str,
    config_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Celery task: generate medical Q&A training data.

    Args:
        job_id: Unique identifier for this generation job (used for
            progress tracking and result retrieval).
        config_dict: Serialised ``TrainingDataConfig`` fields.

    Returns:
        Dict with ``status``, ``output_path``, and ``summary``.
    """
    from ..ml.models import TrainingDataConfig

    logger.info("ML training data generation started (job_id=%s)", job_id)
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if deepseek_key:
        logger.info(
            "LLM provider for RAG/eval: DeepSeekAIService "
            "(DEEPSEEK_MODEL=%s).",
            os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        )
    else:
        logger.info(
            "LLM provider for RAG/eval: OllamaAIService "
            "(OLLAMA_TRAINING_MODEL=%s). Gemini is NOT used.",
            os.environ.get("OLLAMA_TRAINING_MODEL", "llama3.1:8b"),
        )
    start = time.monotonic()

    # Deserialise config
    config = TrainingDataConfig(**config_dict)

    # Override output_dir to use a shared volume path accessible by
    # both the Celery worker (which writes) and the app (which serves
    # downloads). The /app/uploads directory is mounted from the host
    # in both containers.
    config.output_dir = f"/app/uploads/ml_training/{job_id}"

    # Build progress state that will be updated by the callback
    progress_state: Dict[str, Any] = {
        "phase": "initializing",
        "percentage": 0.0,
        "pairs_per_strategy": {},
        "eta_seconds": None,
        "started_at": time.time(),
        "completed_strategies": {},
    }

    # Map generation phase names to strategy keys used in
    # completed_strategies and pairs_per_strategy.
    _phase_to_strategy = {
        "kg_generation": "kg",
        "rag_generation": "rag",
        "umls_generation": "umls_reasoning",
    }

    # Track the previous phase so we can detect strategy completion
    # when the phase transitions away from a *_generation phase.
    _prev_phase: Optional[str] = None

    def _progress_callback(
        phase: str, current: int, total: int
    ) -> None:
        """Report progress via Celery state + Redis persistence."""
        nonlocal _prev_phase

        pct = (current / total * 100.0) if total > 0 else 0.0
        elapsed = time.monotonic() - start
        eta = None
        if current > 0 and pct < 100.0:
            eta = round(elapsed / (pct / 100.0) - elapsed, 1)

        # Detect strategy completion: the previous phase was a
        # *_generation phase and the current phase is different.
        if (
            _prev_phase is not None
            and _prev_phase != phase
            and _prev_phase in _phase_to_strategy
        ):
            completed_key = _phase_to_strategy[_prev_phase]
            pair_count = progress_state[
                "pairs_per_strategy"
            ].get(
                _prev_phase.replace("_generation", ""), 0
            )
            progress_state["completed_strategies"][
                completed_key
            ] = pair_count
            # Persist immediately on strategy completion
            _persist_progress(job_id, progress_state)

        _prev_phase = phase

        progress_state["phase"] = phase
        progress_state["percentage"] = round(pct, 1)
        progress_state["eta_seconds"] = eta

        # Track per-strategy pair counts from phase name
        if phase.endswith("_generation") and current > 0:
            strategy_name = phase.replace("_generation", "")
            progress_state["pairs_per_strategy"][
                strategy_name
            ] = current

        # Update Celery task meta (visible via AsyncResult.info)
        self.update_state(
            state="PROGRESS",
            meta=dict(progress_state),
        )

        # Persist to Redis for hard-timeout recovery
        _persist_progress(job_id, progress_state)

    try:
        # Instantiate generator with live services and run generation.
        # Both _build_training_data_generator and generator.generate
        # are async, so we wrap them in a single asyncio.run() call.
        # After training data, also generate the evaluation set.
        async def _run_pipeline():
            from pathlib import Path as _Path

            from ..ml.models import InstructionTuningPair
            from ..ml.training_data_generator import TrainingDataGenerator

            generator = await _build_training_data_generator(
                strategies=config.strategies,
            )

            # --- Load pre-existing pairs when resuming ---
            pre_existing_pairs: Optional[
                Dict[str, List[InstructionTuningPair]]
            ] = None
            if config.resume_data is not None:
                pre_existing_pairs = {}
                _strategy_to_partial = {
                    "kg": "partial_kg.jsonl",
                    "rag": "partial_rag.jsonl",
                    "umls_reasoning": "partial_umls.jsonl",
                }
                output_dir = _Path(config.output_dir)
                for strategy_name in config.resume_data.get(
                    "strategies", {}
                ):
                    partial_filename = _strategy_to_partial.get(
                        strategy_name
                    )
                    if partial_filename is None:
                        logger.warning(
                            "ML training resume: unknown strategy "
                            "%r, skipping",
                            strategy_name,
                        )
                        continue
                    partial_path = output_dir / partial_filename
                    if partial_path.exists():
                        pairs = TrainingDataGenerator.parse_jsonl(
                            partial_path
                        )
                        pre_existing_pairs[strategy_name] = pairs
                        logger.info(
                            "ML training resume: loaded %d "
                            "pre-existing pairs for strategy "
                            "%r from %s",
                            len(pairs),
                            strategy_name,
                            partial_path,
                        )
                    else:
                        logger.warning(
                            "ML training resume: partial file "
                            "%s not found for strategy %r, "
                            "treating as 0 pre-existing pairs",
                            partial_path,
                            strategy_name,
                        )

            training_result = await generator.generate(
                config=config,
                progress_callback=_progress_callback,
                pre_existing_pairs=(
                    pre_existing_pairs
                    if pre_existing_pairs
                    else None
                ),
            )

            # Generate evaluation set alongside training data.
            # The eval set always needs a RAG service for gold answers,
            # regardless of which training strategies were used.
            eval_set_path = None
            try:
                from ..ml.evaluation_runner import EvaluationRunner
                from ..ml.models import EvaluationConfig

                _progress_callback("eval_generation", 0, 50)

                eval_config = EvaluationConfig(
                    output_dir=config.output_dir,
                )
                eval_runner = EvaluationRunner(eval_config)

                # Collect training questions for exclusion
                training_questions = set()
                if training_result.validation_result.accepted:
                    training_questions = {
                        p.instruction
                        for p in training_result.validation_result.accepted
                    }

                # Build RAG service for eval gold answers if not already
                # available from the training generator
                rag_service = generator._rag
                if rag_service is None:
                    try:
                        deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")
                        if deepseek_key:
                            from ..services.deepseek_ai_service import DeepSeekAIService
                            from ..services.rag_service import RAGService

                            ai_service = DeepSeekAIService()
                            await ai_service.verify_available()

                            rag_service = RAGService(
                                vector_client=generator._vector,
                                ai_service=ai_service,
                            )
                            logger.info(
                                "Built RAG service for eval set generation "
                                "(DeepSeek model=%s)",
                                ai_service.model,
                            )
                        else:
                            from ..services.ollama_ai_service import OllamaAIService
                            from ..services.rag_service import RAGService

                            ai_service = OllamaAIService()
                            await ai_service.verify_available()

                            rag_service = RAGService(
                                vector_client=generator._vector,
                                ai_service=ai_service,
                            )
                            logger.info(
                                "Built RAG service for eval set generation "
                                "(Ollama model=%s)",
                                ai_service.model,
                            )
                    except Exception as rag_exc:
                        logger.warning(
                            "Could not build RAG service for eval: %s. "
                            "Eval set will be skipped.",
                            rag_exc,
                        )

                if rag_service is not None:
                    eval_set = await eval_runner.generate_eval_set(
                        rag_service=rag_service,
                        neo4j_client=generator._neo4j,
                        training_questions=training_questions,
                        count=50,
                        min_semantic_types=5,
                        progress_callback=lambda cur, tot: _progress_callback(
                            "eval_generation", cur, tot
                        ),
                    )

                    if eval_set.questions:
                        from pathlib import Path as _Path
                        eval_out = _Path(config.output_dir) / "eval_set.jsonl"
                        eval_runner.export_eval_set(eval_set, eval_out)
                        eval_set_path = str(eval_out)
                        logger.info(
                            "Eval set generated: %d questions at %s",
                            len(eval_set.questions),
                            eval_out,
                        )
                    else:
                        logger.warning(
                            "Eval set generation produced 0 questions."
                        )
                else:
                    logger.warning(
                        "No RAG service available — skipping eval set. "
                        "Ensure an LLM provider (OpenAI, Gemini, or "
                        "Ollama) is configured."
                    )
            except Exception as eval_exc:
                logger.warning(
                    "Eval set generation failed (non-fatal): %s",
                    eval_exc,
                )

            return training_result, eval_set_path

        result, eval_set_path = asyncio.run(_run_pipeline())

        # Final progress update
        progress_state["phase"] = "completed"
        progress_state["percentage"] = 100.0
        progress_state["eta_seconds"] = 0
        _persist_progress(job_id, progress_state)

        elapsed = round(time.monotonic() - start, 2)
        logger.info(
            "ML training data generation completed (job_id=%s) in %.1fs — "
            "%d pairs exported to %s",
            job_id,
            elapsed,
            result.dataset_summary.total_pairs,
            result.output_path,
        )

        summary = {
            "total_pairs": result.dataset_summary.total_pairs,
            "pairs_per_strategy": result.dataset_summary.pairs_per_strategy,
            "dedup_removed": result.dataset_summary.dedup_removed,
            "avg_response_length": result.dataset_summary.avg_response_length,
            "pass_rate": result.validation_result.pass_rate,
            "generation_time_seconds": elapsed,
        }

        return {
            "status": "completed",
            "job_id": job_id,
            "output_path": result.output_path,
            "eval_set_path": eval_set_path,
            "summary": summary,
        }

    except Exception as exc:
        elapsed = round(time.monotonic() - start, 2)
        logger.error(
            "ML training data generation failed (job_id=%s) after %.1fs: %s",
            job_id,
            elapsed,
            exc,
        )

        # Persist failure state for recovery
        progress_state["phase"] = "failed"
        progress_state["error"] = str(exc)
        _persist_progress(job_id, progress_state)

        # Re-raise so Celery marks the task as FAILURE
        raise
