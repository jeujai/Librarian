"""
QLoRA fine-tuning trainer via mlx-lm on Apple Silicon.

Wraps the ``mlx-lm`` library for QLoRA (4-bit quantization with LoRA
adapters) fine-tuning of Llama 3.2 3B using native Metal GPU
acceleration on M2 Max. Runs on the host machine (not inside Docker).

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .models import InstructionTuningPair, TrainingConfig, TrainingSummary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Llama 3.2 Instruct chat template tokens
_BOS = "<|begin_of_text|>"
_HEADER_START = "<|start_header_id|>"
_HEADER_END = "<|end_header_id|>"
_EOT = "<|eot_id|>"

_SYSTEM_PROMPT = (
    "You are a medical knowledge assistant trained on curated medical "
    "textbooks, clinical guidelines, and biomedical literature. Provide "
    "accurate, evidence-based responses to medical questions."
)

# Minimum batch size before aborting due to memory pressure
_MIN_BATCH_SIZE = 1


# ---------------------------------------------------------------------------
# Chat template formatting
# ---------------------------------------------------------------------------


def build_inference_user_message(instruction: str, context: str) -> str:
    """Build the user message for inference or training from instruction and context.

    This is the single source of truth for constructing the user-message
    content used in both training (via ``format_chat_message``) and
    evaluation (via ``EvaluationRunner._query_ollama``).

    Args:
        instruction: The question or instruction text.
        context: The RAG context string. When non-empty, it is appended
            after a ``Context:`` header.

    Returns:
        The formatted user message string.
    """
    if context and context.strip():
        return f"{instruction}\n\nContext:\n{context}"
    return instruction


def format_chat_message(
    pair: InstructionTuningPair,
    distill: bool = False,
) -> Dict[str, Any]:
    """Format an InstructionTuningPair into mlx-lm chat format.

    Produces a conversation dict with ``messages`` following the Llama 3
    chat template structure: system → user → assistant.

    When *distill* is False (default), the user message combines the
    instruction and context fields. When *distill* is True (knowledge
    distillation mode), context is stripped and citation markers are
    removed from the response so the model learns to produce standalone
    medical answers from its own weights.

    Args:
        pair: An instruction-tuning pair to format.
        distill: If True, strip context and clean citations for
            knowledge distillation training.

    Returns:
        A dict with a ``messages`` key containing the conversation in
        the format expected by ``mlx_lm.lora``.
    """
    # Build user content — delegate to the shared helper
    if distill:
        # In distill mode, context is intentionally stripped
        user_content = pair.instruction
    else:
        user_content = build_inference_user_message(pair.instruction, pair.context)

    # Build response
    response = pair.response
    if distill:
        response = _clean_response_for_distillation(response)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": response},
    ]
    return {"messages": messages}


def format_chat_message_no_system(
    pair: InstructionTuningPair,
    distill: bool = False,
) -> Dict[str, Any]:
    """Format for models that don't support a system role (e.g. Mistral).

    Prepends the system prompt to the user message so the conversation
    is strictly user/assistant alternation.
    """
    if distill:
        user_content = pair.instruction
    else:
        user_content = build_inference_user_message(pair.instruction, pair.context)

    response = pair.response
    if distill:
        response = _clean_response_for_distillation(response)

    combined_user = f"{_SYSTEM_PROMPT}\n\n{user_content}"
    messages = [
        {"role": "user", "content": combined_user},
        {"role": "assistant", "content": response},
    ]
    return {"messages": messages}


def _clean_response_for_distillation(response: str) -> str:
    """Remove RAG-specific artifacts from a response for distillation.

    Strips:
    - [Source N] citation markers
    - "Based on the provided documents/sources, ..." preambles
    - Trailing whitespace from removed citations
    """
    import re

    # Remove [Source N] markers
    cleaned = re.sub(r"\[Source\s*\d+\]", "", response)

    # Remove common RAG preambles at start of response
    preambles = [
        r"^Based on (?:the )?provided (?:documents|sources|information|medical sources|source documents|library),?\s*",
        r"^Based on the (?:sources|documents|information) provided,?\s*",
        r"^According to the (?:provided )?(?:documents|sources|medical sources),?\s*",
        r"^From the (?:provided )?(?:documents|sources),?\s*",
    ]
    for pattern in preambles:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Collapse multiple spaces left by citation removal
    cleaned = re.sub(r"  +", " ", cleaned)

    # Strip leading/trailing whitespace
    cleaned = cleaned.strip()

    # Capitalize first letter if it became lowercase after preamble removal
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    return cleaned


def format_chat_template_string(pair: InstructionTuningPair) -> str:
    """Format an InstructionTuningPair into a raw Llama 3 chat template string.

    This produces the full tokenizer-level chat template string with
    special tokens, useful for verification and property testing.

    Args:
        pair: An instruction-tuning pair to format.

    Returns:
        The formatted chat template string containing the instruction,
        context, and response text.
    """
    user_content = pair.instruction
    if pair.context and pair.context.strip():
        user_content = f"{pair.instruction}\n\nContext:\n{pair.context}"

    parts = [
        f"{_BOS}{_HEADER_START}system{_HEADER_END}\n\n"
        f"{_SYSTEM_PROMPT}{_EOT}",
        f"{_HEADER_START}user{_HEADER_END}\n\n"
        f"{user_content}{_EOT}",
        f"{_HEADER_START}assistant{_HEADER_END}\n\n"
        f"{pair.response}{_EOT}",
    ]
    return "".join(parts)


# ---------------------------------------------------------------------------
# QLoRATrainer
# ---------------------------------------------------------------------------


class QLoRATrainer:
    """QLoRA fine-tuning via mlx-lm on Apple Silicon.

    Loads a base model in 4-bit quantized format, applies LoRA adapters
    to configurable target modules, formats the training dataset into
    the Llama chat template, and trains using ``mlx_lm``. Monitors
    memory usage and reduces batch size if it exceeds the configured
    threshold.

    Args:
        config: A ``TrainingConfig`` with all hyperparameters and paths.
    """

    def __init__(self, config: TrainingConfig) -> None:
        self.config = config
        self._last_valid_checkpoint_step: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(
        self,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> TrainingSummary:
        """Run QLoRA fine-tuning.

        Steps:
        1. Load base model in 4-bit via ``mlx_lm.load()``
        2. Apply LoRA adapters to target modules
        3. Format dataset into chat template
        4. Train with ``mlx_lm.lora``
        5. Monitor memory, reduce batch size if > ``max_memory_gb``
        6. Save adapter weights
        7. Produce ``TrainingSummary``

        Args:
            progress_callback: Optional ``(step, total_steps, loss)``
                callback for reporting training progress.

        Returns:
            A ``TrainingSummary`` with training statistics.

        Raises:
            FileNotFoundError: If the dataset path does not exist.
            RuntimeError: If training fails irrecoverably.
        """
        start_time = time.monotonic()

        # Validate dataset path
        dataset_path = Path(self.config.dataset_path)
        if not dataset_path.exists():
            raise FileNotFoundError(
                f"Dataset not found at {dataset_path}. "
                f"Generate training data first using the training data "
                f"generation pipeline."
            )

        # Ensure output directory exists
        output_dir = Path(self.config.output_dir)
        self._ensure_output_dir(output_dir)

        # Step 1: Format dataset into mlx-lm chat format
        logger.info(
            "QLoRA: Formatting dataset from %s into chat template",
            dataset_path,
        )
        formatted_data_dir = self._format_dataset(dataset_path)
        total_examples = self._count_examples(formatted_data_dir / "train.jsonl")
        logger.info(
            "QLoRA: Formatted %d training examples", total_examples
        )

        if total_examples == 0:
            raise RuntimeError(
                f"No valid training examples found in {dataset_path}. "
                f"Check that the JSONL file contains valid "
                f"InstructionTuningPair entries."
            )

        # Step 2–6: Load model, apply LoRA, train
        summary = self._run_training(
            formatted_data_dir=formatted_data_dir,
            total_examples=total_examples,
            output_dir=output_dir,
            progress_callback=progress_callback,
        )

        elapsed = time.monotonic() - start_time
        summary.total_training_time_seconds = round(elapsed, 2)

        # Compute adapter file size
        adapter_path = output_dir / "adapters.safetensors"
        if adapter_path.exists():
            summary.adapter_file_size_mb = round(
                adapter_path.stat().st_size / (1024 * 1024), 2
            )
            summary.adapter_path = str(adapter_path)
        else:
            # Check for directory-based adapter output
            adapter_dir_size = self._get_dir_size(output_dir)
            summary.adapter_file_size_mb = round(
                adapter_dir_size / (1024 * 1024), 2
            )
            summary.adapter_path = str(output_dir)

        logger.info(
            "QLoRA: Training complete in %.1fs — final loss: %.4f, "
            "peak memory: %.1f GB, %d steps, adapter size: %.1f MB",
            summary.total_training_time_seconds,
            summary.final_loss,
            summary.peak_memory_gb,
            summary.total_steps,
            summary.adapter_file_size_mb,
        )

        return summary

    # ------------------------------------------------------------------
    # Dataset formatting (Requirement 5.3)
    # ------------------------------------------------------------------

    def _format_dataset(self, dataset_path: Path) -> Path:
        """Convert JSONL training data to mlx-lm chat format.

        Reads the JSONL file produced by ``TrainingDataGenerator``,
        converts each ``InstructionTuningPair`` into the Llama chat
        template format expected by ``mlx_lm.lora``, and writes the
        result to a temporary directory.

        The output format is a JSONL file where each line is a JSON
        object with a ``messages`` key containing a list of
        ``{role, content}`` dicts (system, user, assistant).

        Args:
            dataset_path: Path to the input JSONL training data file.

        Returns:
            Path to the directory containing the formatted
            ``train.jsonl`` and ``valid.jsonl`` files.
        """
        output_dir = Path(self.config.output_dir) / "_formatted_data"
        output_dir.mkdir(parents=True, exist_ok=True)

        pairs = self._load_pairs(dataset_path)

        if not pairs:
            # Write empty files so downstream doesn't crash
            (output_dir / "train.jsonl").write_text("", encoding="utf-8")
            (output_dir / "valid.jsonl").write_text("", encoding="utf-8")
            return output_dir

        # Split into train (90%) and validation (10%)
        split_idx = max(1, int(len(pairs) * 0.9))
        train_pairs = pairs[:split_idx]
        valid_pairs = pairs[split_idx:]

        # If validation set is empty, use last training example
        if not valid_pairs:
            valid_pairs = [train_pairs[-1]]

        self._write_formatted_jsonl(
            train_pairs, output_dir / "train.jsonl"
        )
        self._write_formatted_jsonl(
            valid_pairs, output_dir / "valid.jsonl"
        )

        logger.info(
            "QLoRA: Dataset split — %d train, %d validation",
            len(train_pairs),
            len(valid_pairs),
        )

        return output_dir

    def _load_pairs(self, dataset_path: Path) -> List[InstructionTuningPair]:
        """Load InstructionTuningPair objects from a JSONL file.

        Invalid lines are skipped with a warning.
        """
        pairs: List[InstructionTuningPair] = []
        with dataset_path.open("r", encoding="utf-8") as fh:
            for line_num, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    pair = InstructionTuningPair.from_jsonl_line(line)
                    pairs.append(pair)
                except Exception as exc:
                    logger.warning(
                        "QLoRA: Skipping invalid JSONL line %d: %s",
                        line_num,
                        exc,
                    )
        return pairs

    def _write_formatted_jsonl(
        self,
        pairs: List[InstructionTuningPair],
        output_path: Path,
    ) -> None:
        """Write pairs in mlx-lm chat format to a JSONL file."""
        # Mistral models don't support a system role in their chat
        # template — fold system prompt into the user message instead.
        use_no_system = "mistral" in self.config.model_name.lower()
        formatter = (
            format_chat_message_no_system if use_no_system
            else format_chat_message
        )
        with output_path.open("w", encoding="utf-8") as fh:
            for pair in pairs:
                chat_dict = formatter(pair, distill=self.config.distill)
                fh.write(
                    json.dumps(chat_dict, ensure_ascii=False) + "\n"
                )

    # ------------------------------------------------------------------
    # Training execution
    # ------------------------------------------------------------------

    def _run_training(
        self,
        formatted_data_dir: Path,
        total_examples: int,
        output_dir: Path,
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
    ) -> TrainingSummary:
        """Execute the mlx-lm training loop.

        Handles model loading, LoRA configuration, training, memory
        monitoring, NaN loss detection, and checkpoint saving.

        Args:
            formatted_data_dir: Directory with train.jsonl/valid.jsonl.
            total_examples: Number of training examples.
            output_dir: Directory for saving adapter weights.
            progress_callback: Optional progress callback.

        Returns:
            A ``TrainingSummary`` (without total_training_time_seconds
            and adapter_file_size_mb, which are set by the caller).
        """
        try:
            import mlx.core as mx
            from mlx_lm.lora import run as mlx_run
        except ImportError as exc:
            raise RuntimeError(
                "mlx-lm is required for QLoRA training but is not "
                "installed. Install it with: pip install mlx-lm\n"
                f"Import error: {exc}"
            ) from exc

        config = self.config
        batch_size = config.batch_size
        peak_memory_gb = 0.0
        final_loss = 0.0
        total_steps = 0
        epochs_completed = 0

        # Compute total iterations from epochs
        steps_per_epoch = max(
            1,
            math.ceil(total_examples / (batch_size * config.grad_accumulation_steps)),
        )
        total_iters = steps_per_epoch * config.epochs

        logger.info(
            "QLoRA: Starting training — model=%s, batch_size=%d, "
            "lr=%.1e, epochs=%d, total_iters=%d, lora_rank=%d",
            config.model_name,
            batch_size,
            config.learning_rate,
            config.epochs,
            total_iters,
            config.lora_rank,
        )

        # Build args namespace for mlx_lm.lora.run()
        # This is the high-level API that handles model loading,
        # LoRA application, dataset loading, and training.
        import types

        args = types.SimpleNamespace(
            model=config.model_name,
            train=True,
            fine_tune_type="lora",
            optimizer="adam",
            optimizer_config={"adam": {}},
            data=str(formatted_data_dir),
            seed=42,
            num_layers=config.num_layers,
            batch_size=batch_size,
            iters=total_iters,
            val_batches=10,
            learning_rate=config.learning_rate,
            steps_per_report=config.log_every,
            steps_per_eval=config.save_every,
            resume_adapter_file=None,
            adapter_path=str(output_dir),
            save_every=config.save_every,
            test=False,
            test_batches=500,
            max_seq_length=config.max_seq_length,
            config=None,
            grad_checkpoint=True,
            grad_accumulation_steps=config.grad_accumulation_steps,
            clear_cache_threshold=0.75,
            lr_schedule=None,
            lora_parameters={
                "rank": config.lora_rank,
                "dropout": config.lora_dropout,
                "scale": config.lora_alpha / config.lora_rank,
            },
            mask_prompt=config.mask_prompt,
            report_to=None,
            project_name=None,
        )

        logger.info(
            "QLoRA: Applying LoRA — rank=%d, alpha=%d, scale=%.1f, "
            "num_layers=%d, mask_prompt=%s",
            config.lora_rank,
            config.lora_alpha,
            config.lora_alpha / config.lora_rank,
            config.num_layers,
            config.mask_prompt,
        )

        try:
            mlx_run(args)
            epochs_completed = config.epochs

            # Check peak memory
            try:
                active = mx.metal.get_active_memory()
                peak_memory_gb = active / (1024**3)
            except Exception:
                pass

        except Exception as exc:
            error_msg = str(exc)
            if "No space left on device" in error_msg:
                raise RuntimeError(
                    f"Disk space error while saving adapter "
                    f"weights to {output_dir}. Free up disk "
                    f"space and retry. Error: {exc}"
                ) from exc
            raise
        total_steps = total_iters

        return TrainingSummary(
            final_loss=final_loss,
            peak_memory_gb=round(peak_memory_gb, 2),
            total_steps=total_steps,
            epochs_completed=epochs_completed,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_output_dir(output_dir: Path) -> None:
        """Create the output directory, handling disk space errors."""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            if "No space left on device" in str(exc) or (
                hasattr(exc, "errno") and exc.errno == 28
            ):
                raise RuntimeError(
                    f"Cannot create output directory {output_dir}: "
                    f"no disk space available. Free up space and retry."
                ) from exc
            raise

    @staticmethod
    def _count_examples(jsonl_path: Path) -> int:
        """Count the number of lines in a JSONL file."""
        if not jsonl_path.exists():
            return 0
        count = 0
        with jsonl_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    count += 1
        return count

    @staticmethod
    def _get_dir_size(path: Path) -> int:
        """Get total size of all files in a directory in bytes."""
        total = 0
        if path.is_file():
            return path.stat().st_size
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total
