"""
Data models for the Medical Knowledge Fine-Tuning Pipeline.

This module defines all data structures used across the three pipelines:
training data generation, QLoRA fine-tuning, and evaluation. Models that
cross serialization boundaries (JSONL I/O, API request/response) use
Pydantic for validation. Internal-only types use plain dataclasses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_STRATEGIES = ("kg", "rag", "umls_reasoning")
VALID_DIFFICULTY_LEVELS = ("single-concept", "multi-concept", "reasoning")


# ---------------------------------------------------------------------------
# Pydantic models — used at serialization boundaries (JSONL, API)
# ---------------------------------------------------------------------------


class PairMetadata(BaseModel):
    """Metadata attached to every instruction-tuning pair.

    Serialized as part of the JSONL training data format.
    """

    strategy: str = Field(
        ...,
        description="Generation strategy: 'kg', 'rag', or 'umls_reasoning'",
    )
    source_concepts: List[str] = Field(
        default_factory=list,
        description="UMLS CUIs or concept names involved",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    source_document: Optional[str] = Field(
        default=None,
        description="Source document title",
    )
    chunk_ids: Optional[List[str]] = Field(
        default=None,
        description="IDs of source chunks used",
    )
    relationship_chain: Optional[str] = Field(
        default=None,
        description="Relationship chain for UMLS reasoning pairs",
    )
    semantic_type: Optional[str] = Field(
        default=None,
        description=(
            "UMLS semantic type of the source concept (e.g., 'Diagnostic "
            "Procedure', 'Pharmacologic Substance'). Propagated from "
            "SeedQuestion.semantic_type so per-type training-data balance "
            "can be observed on disk. None for legacy pairs."
        ),
    )

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in VALID_STRATEGIES:
            raise ValueError(
                f"strategy must be one of {VALID_STRATEGIES}, got '{v}'"
            )
        return v


class InstructionTuningPair(BaseModel):
    """A single instruction-tuning training example.

    This is the core data unit serialized to/from JSONL. It supports
    JSON serialization with consistent field ordering and UTF-8 encoding,
    and round-trip equality via ``parse(print(x)) == x``.
    """

    instruction: str = Field(
        ..., min_length=1, description="The question / instruction"
    )
    context: str = Field(
        ..., min_length=1, description="Supporting context"
    )
    response: str = Field(
        ..., min_length=1, description="The answer / response"
    )
    metadata: PairMetadata

    # ------------------------------------------------------------------
    # Serialization helpers for JSONL round-trip
    # ------------------------------------------------------------------

    def to_jsonl_dict(self) -> Dict[str, Any]:
        """Serialize to a dict with consistent field ordering for JSONL.

        Field order: instruction, context, response, metadata.
        """
        return {
            "instruction": self.instruction,
            "context": self.context,
            "response": self.response,
            "metadata": self.metadata.model_dump(exclude_none=True),
        }

    def to_jsonl_line(self) -> str:
        """Serialize to a single JSON line (UTF-8, no trailing newline)."""
        return json.dumps(self.to_jsonl_dict(), ensure_ascii=False)

    @classmethod
    def from_jsonl_line(cls, line: str) -> "InstructionTuningPair":
        """Deserialize from a single JSON line."""
        data = json.loads(line)
        return cls.model_validate(data)

    # ------------------------------------------------------------------
    # Equality — needed for round-trip property testing
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InstructionTuningPair):
            return NotImplemented
        return (
            self.instruction == other.instruction
            and self.context == other.context
            and self.response == other.response
            and self.metadata == other.metadata
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.instruction,
                self.context,
                self.response,
                self.metadata.strategy,
                self.metadata.confidence_score,
            )
        )


# ---------------------------------------------------------------------------
# Seed question model (used by RAG_QA_Strategy)
# ---------------------------------------------------------------------------


class SeedQuestion(BaseModel):
    """A seed question generated for the RAG Q&A strategy."""

    question: str = Field(..., min_length=1, description="The question text")
    source: str = Field(
        ...,
        description="Source of the seed question: 'umls_concept', 'chapter_heading', or 'template'",
    )
    semantic_type: Optional[str] = Field(
        default=None, description="UMLS semantic type if applicable"
    )
    concept_name: Optional[str] = Field(
        default=None, description="Concept name used to generate the question"
    )


# ---------------------------------------------------------------------------
# Configuration dataclasses — internal-only, no serialization boundary
# ---------------------------------------------------------------------------


@dataclass
class TrainingDataConfig:
    """Configuration for training data generation."""

    target_pair_count: int = 7500
    strategies: List[str] = field(
        default_factory=lambda: ["kg", "umls_reasoning"]
    )
    random_seed: int = 42
    min_confidence_score: float = 0.80
    min_chunk_tokens: int = 50
    similarity_threshold: float = 0.95
    output_dir: str = "./training_data"
    semantic_types: Optional[List[str]] = None
    resume_data: Optional[Dict] = None


@dataclass
class TrainingConfig:
    """Configuration for QLoRA fine-tuning."""

    model_name: str = "mlx-community/Llama-3.2-3B-Instruct-4bit"
    dataset_path: str = ""
    output_dir: str = "./adapters"
    lora_rank: int = 16
    lora_alpha: int = 32
    num_layers: int = 32
    lora_dropout: float = 0.0
    mask_prompt: bool = True
    distill: bool = False
    target_modules: List[str] = field(
        default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"]
    )
    learning_rate: float = 1e-4
    batch_size: int = 4
    grad_accumulation_steps: int = 4
    epochs: int = 3
    warmup_ratio: float = 0.03
    max_memory_gb: float = 28.0
    save_every: int = 100
    log_every: int = 10
    max_seq_length: int = 4096


@dataclass
class ExportConfig:
    """Configuration for GGUF export."""

    adapter_path: str = "./adapters"
    base_model: str = "mlx-community/Llama-3.2-3B-Instruct-4bit"
    output_dir: str = "./export"
    model_name: str = "librarian-medical-3b"
    quantization: str = "Q4_K_M"
    register_ollama: bool = True
    system_prompt: str = (
        "You are a medical knowledge assistant trained on curated medical "
        "textbooks, clinical guidelines, and biomedical literature. Provide "
        "accurate, evidence-based responses to medical questions."
    )


@dataclass
class EvaluationConfig:
    """Configuration for before/after model evaluation."""

    eval_set_path: str = ""
    base_model: str = "llama3.2:3b"
    finetuned_model: str = "librarian-medical-3b"
    output_dir: str = "./evaluation"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    min_semantic_types: int = 5
    eval_count: int = 50
    improvement_threshold: float = 0.05


# ---------------------------------------------------------------------------
# Evaluation data models — Pydantic for JSONL serialization
# ---------------------------------------------------------------------------


class EvaluationQuestion(BaseModel):
    """A single evaluation question with its gold-standard answer."""

    question: str = Field(..., min_length=1)
    gold_answer: str = Field(..., min_length=1)
    semantic_type: str = Field(..., min_length=1)
    source_citations: List[str] = Field(..., min_length=1)
    difficulty_level: str = Field(..., min_length=1)
    context: str = Field(
        default="",
        description="Retrieved document context for RAG-style evaluation",
    )

    @field_validator("difficulty_level")
    @classmethod
    def validate_difficulty(cls, v: str) -> str:
        if v not in VALID_DIFFICULTY_LEVELS:
            raise ValueError(
                f"difficulty_level must be one of {VALID_DIFFICULTY_LEVELS}, got '{v}'"
            )
        return v


class EvaluationSet(BaseModel):
    """A complete evaluation question set."""

    questions: List[EvaluationQuestion]
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# LLM Judge models — Pydantic for validation and serialization
# ---------------------------------------------------------------------------


class DimensionScores(BaseModel):
    """Scores on four clinical evaluation dimensions (1–5 integer scale)."""

    factual_accuracy: int = Field(..., ge=1, le=5)
    completeness: int = Field(..., ge=1, le=5)
    clinical_relevance: int = Field(..., ge=1, le=5)
    coherence: int = Field(..., ge=1, le=5)


class JudgeVerdict(BaseModel):
    """Parsed output from a single judge call."""

    response_a_scores: DimensionScores
    response_b_scores: DimensionScores
    winner: str = Field(...)  # "A", "B", or "TIE"
    explanation: str = Field(default="")

    @field_validator("winner")
    @classmethod
    def validate_winner(cls, v: str) -> str:
        v_upper = v.strip().upper()
        if v_upper not in ("A", "B", "TIE"):
            return "TIE"  # treat unrecognized as tie
        return v_upper


class JudgeResult(BaseModel):
    """Result of judging a single question, with model identity mapped."""

    base_scores: DimensionScores
    finetuned_scores: DimensionScores
    winner: str  # "base", "finetuned", or "tie"
    explanation: str
    position_label: str  # "base_is_A" or "base_is_B"


# ---------------------------------------------------------------------------
# Scoring and comparison report models
# ---------------------------------------------------------------------------


@dataclass
class ResponseScore:
    """Scores for a single model response against a gold answer."""

    factual_accuracy: int  # 1–5
    completeness: int  # 1–5
    clinical_relevance: int  # 1–5
    coherence: int  # 1–5


@dataclass
class QuestionResult:
    """Per-question comparison between base and fine-tuned model."""

    question: str
    gold_answer: str
    base_response: str
    finetuned_response: str
    base_score: ResponseScore
    finetuned_score: ResponseScore
    semantic_type: str
    difficulty_level: str
    winner: str = ""  # "base", "finetuned", or "tie"
    judge_explanation: str = ""
    position_label: str = ""  # "base_is_A" or "base_is_B"
    base_similarity: float = 0.0  # cosine sim of base response vs gold
    finetuned_similarity: float = 0.0  # cosine sim of ft response vs gold


@dataclass
class ComparisonReport:
    """Aggregate comparison report for before/after evaluation."""

    results: List[QuestionResult]
    win_rate: float
    mean_score_delta: float
    improvement_delta: float
    by_semantic_type: Dict[str, Dict[str, float]]
    by_difficulty: Dict[str, Dict[str, float]]
    flagged: bool  # True if improvement_delta < threshold or >50% judge failures
    recommendations: List[str]
    judge_stats: Dict[str, Any] = field(default_factory=dict)
    base_mean_scores: Dict[str, float] = field(default_factory=dict)
    finetuned_mean_scores: Dict[str, float] = field(default_factory=dict)
    # Similarity-based metrics (embedding cosine sim vs gold answer)
    base_mean_similarity: float = 0.0
    finetuned_mean_similarity: float = 0.0
    similarity_delta: float = 0.0
    similarity_by_semantic_type: Dict[str, Dict[str, float]] = field(
        default_factory=dict
    )


# ---------------------------------------------------------------------------
# Result / summary dataclasses — returned by pipeline stages
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of dataset quality validation."""

    accepted: List[InstructionTuningPair]
    rejected: List[InstructionTuningPair]
    rejection_reasons: Dict[str, List[str]]  # pair instruction → list of reasons
    total: int = 0
    pass_rate: float = 0.0

    def __post_init__(self) -> None:
        if self.total == 0:
            self.total = len(self.accepted) + len(self.rejected)
        if self.total > 0 and self.pass_rate == 0.0:
            self.pass_rate = len(self.accepted) / self.total


@dataclass
class DatasetSummary:
    """Summary statistics for an exported training dataset."""

    total_pairs: int = 0
    pairs_per_strategy: Dict[str, int] = field(default_factory=dict)
    dedup_removed: int = 0
    avg_response_length: float = 0.0
    concept_coverage: Dict[str, int] = field(default_factory=dict)
    confidence_distribution: Dict[str, int] = field(default_factory=dict)
    output_path: str = ""


@dataclass
class TrainingDataResult:
    """Result of the full training data generation pipeline."""

    dataset_summary: DatasetSummary
    validation_result: ValidationResult
    output_path: str = ""
    generation_time_seconds: float = 0.0


@dataclass
class TrainingSummary:
    """Summary of a completed QLoRA fine-tuning run."""

    total_training_time_seconds: float = 0.0
    final_loss: float = 0.0
    peak_memory_gb: float = 0.0
    total_steps: int = 0
    adapter_file_size_mb: float = 0.0
    adapter_path: str = ""
    epochs_completed: int = 0


@dataclass
class ExportResult:
    """Result of GGUF export and Ollama registration."""

    gguf_path: str = ""
    modelfile_path: str = ""
    model_name: str = ""
    gguf_size_mb: float = 0.0
    quantization: str = ""
    ollama_registered: bool = False
    manual_instructions: Optional[str] = None
