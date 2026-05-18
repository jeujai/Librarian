"""
CLI for QLoRA fine-tuning of medical language models.

Entry point::

    python -m multimodal_librarian.ml.finetune --dataset <path>

Accepts all ``TrainingConfig`` hyperparameters as CLI arguments, displays
a progress bar with current step / elapsed time / ETA using ``rich``,
and provides descriptive error messages with corrective suggestions on
failure.

Requirements: 10.1, 10.4, 10.5
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for fine-tuning."""
    parser = argparse.ArgumentParser(
        prog="python -m multimodal_librarian.ml.finetune",
        description=(
            "Fine-tune Llama 3.2 3B on a medical Q&A dataset using "
            "QLoRA via Apple MLX with Metal GPU acceleration."
        ),
    )

    # Required
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="Path to the JSONL training dataset produced by the data generation pipeline.",
    )

    # Model
    parser.add_argument(
        "--model",
        type=str,
        default="mlx-community/Llama-3.2-3B-Instruct-4bit",
        help="HuggingFace model name or local path (default: mlx-community/Llama-3.2-3B-Instruct-4bit).",
    )

    # Output
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./adapters",
        help="Directory to save LoRA adapter weights (default: ./adapters).",
    )

    # LoRA hyperparameters
    parser.add_argument(
        "--lora-rank",
        type=int,
        default=16,
        help="LoRA rank (default: 16).",
    )
    parser.add_argument(
        "--lora-alpha",
        type=int,
        default=32,
        help="LoRA alpha scaling factor (default: 32).",
    )
    parser.add_argument(
        "--num-layers",
        type=int,
        default=32,
        help="Number of transformer layers to apply LoRA to (default: 32).",
    )
    parser.add_argument(
        "--lora-dropout",
        type=float,
        default=0.0,
        help="LoRA dropout rate (default: 0.0).",
    )
    parser.add_argument(
        "--mask-prompt",
        action="store_true",
        default=True,
        help="Only train on assistant response tokens (default: True).",
    )
    parser.add_argument(
        "--no-mask-prompt",
        action="store_false",
        dest="mask_prompt",
        help="Train on all tokens including system/user prompt.",
    )
    parser.add_argument(
        "--distill",
        action="store_true",
        default=False,
        help="Knowledge distillation mode: strip context and citations from training pairs.",
    )
    parser.add_argument(
        "--target-modules",
        type=str,
        nargs="+",
        default=["q_proj", "v_proj", "k_proj", "o_proj"],
        help="Target modules for LoRA adapters (default: q_proj v_proj k_proj o_proj).",
    )

    # Training hyperparameters
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=1e-4,
        help="Learning rate (default: 1e-4).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Training batch size (default: 4).",
    )
    parser.add_argument(
        "--grad-accumulation-steps",
        type=int,
        default=4,
        help="Gradient accumulation steps (default: 4).",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs (default: 3).",
    )
    parser.add_argument(
        "--warmup-ratio",
        type=float,
        default=0.03,
        help="Warmup ratio for learning rate scheduler (default: 0.03).",
    )

    # Memory / checkpointing
    parser.add_argument(
        "--max-memory-gb",
        type=float,
        default=28.0,
        help="Maximum GPU memory in GB before batch size reduction (default: 28.0).",
    )
    parser.add_argument(
        "--max-seq-length",
        type=int,
        default=4096,
        help="Max sequence length in tokens; longer examples truncated (default: 3072).",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=100,
        help="Save a checkpoint every N steps (default: 100).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=10,
        help="Log training metrics every N steps (default: 10).",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the fine-tuning CLI.

    Returns 0 on success, 1 on failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Validate dataset path early
    # ------------------------------------------------------------------
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        _print_error(
            f"Dataset file not found: {dataset_path}",
            suggestion=(
                "Generate training data first using the API endpoint "
                "POST /api/v1/ml/training-data/generate, or provide "
                "a valid path to an existing JSONL dataset."
            ),
        )
        return 1

    if not dataset_path.is_file():
        _print_error(
            f"Dataset path is not a file: {dataset_path}",
            suggestion="Provide a path to a JSONL file, not a directory.",
        )
        return 1

    # ------------------------------------------------------------------
    # Build TrainingConfig from CLI args
    # ------------------------------------------------------------------
    from .models import TrainingConfig

    config = TrainingConfig(
        model_name=args.model,
        dataset_path=str(dataset_path),
        output_dir=args.output_dir,
        lora_rank=args.lora_rank,
        lora_alpha=args.lora_alpha,
        num_layers=args.num_layers,
        lora_dropout=args.lora_dropout,
        mask_prompt=args.mask_prompt,
        distill=args.distill,
        target_modules=args.target_modules,
        learning_rate=args.learning_rate,
        batch_size=args.batch_size,
        grad_accumulation_steps=args.grad_accumulation_steps,
        epochs=args.epochs,
        warmup_ratio=args.warmup_ratio,
        max_memory_gb=args.max_memory_gb,
        save_every=args.save_every,
        log_every=args.log_every,
        max_seq_length=args.max_seq_length,
    )

    # ------------------------------------------------------------------
    # Run training with rich progress display
    # ------------------------------------------------------------------
    try:
        from rich.console import Console
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            SpinnerColumn,
            TextColumn,
            TimeElapsedColumn,
            TimeRemainingColumn,
        )
    except ImportError:
        _print_error(
            "The 'rich' library is required for CLI progress display.",
            suggestion="Install it with: pip install rich",
        )
        return 1

    console = Console()

    console.print(
        "\n[bold cyan]Medical Knowledge Fine-Tuning[/bold cyan]",
    )
    console.print(f"  Model:       {config.model_name}")
    console.print(f"  Dataset:     {config.dataset_path}")
    console.print(f"  Output:      {config.output_dir}")
    console.print(f"  LoRA rank:   {config.lora_rank}")
    console.print(f"  LR:          {config.learning_rate}")
    console.print(f"  Batch size:  {config.batch_size}")
    console.print(f"  Epochs:      {config.epochs}")
    console.print()

    from .qlora_trainer import QLoRATrainer

    trainer = QLoRATrainer(config)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    # We don't know total steps upfront — the trainer computes them.
    # Start with an indeterminate task, then update once we get the
    # first progress callback.
    task_id = None
    start_time = time.monotonic()

    def _progress_callback(step: int, total_steps: int, loss: float) -> None:
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "[cyan]Training", total=total_steps
            )
        progress.update(
            task_id,
            completed=step,
            total=total_steps,
            description=f"[cyan]Training (loss={loss:.4f})",
        )

    try:
        with progress:
            summary = trainer.train(progress_callback=_progress_callback)
    except FileNotFoundError as exc:
        _print_error(str(exc), suggestion="Check the --dataset path.")
        return 1
    except RuntimeError as exc:
        _print_error(str(exc))
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Training interrupted by user.[/yellow]")
        return 1

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    elapsed = time.monotonic() - start_time
    console.print()
    console.print("[bold green]Training complete![/bold green]")
    console.print(f"  Total time:      {_format_duration(elapsed)}")
    console.print(f"  Final loss:      {summary.final_loss:.4f}")
    console.print(f"  Peak memory:     {summary.peak_memory_gb:.1f} GB")
    console.print(f"  Total steps:     {summary.total_steps}")
    console.print(f"  Epochs:          {summary.epochs_completed}")
    console.print(f"  Adapter size:    {summary.adapter_file_size_mb:.1f} MB")
    console.print(f"  Adapter path:    {summary.adapter_path}")
    console.print()
    console.print(
        "[dim]Next step: export to GGUF with "
        "'python -m multimodal_librarian.ml.export "
        f"--adapter {summary.adapter_path}'[/dim]"
    )

    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_error(message: str, suggestion: str | None = None) -> None:
    """Print a formatted error message to stderr."""
    try:
        from rich.console import Console

        console = Console(stderr=True)
        console.print(f"\n[bold red]Error:[/bold red] {message}")
        if suggestion:
            console.print(f"[yellow]Suggestion:[/yellow] {suggestion}")
        console.print()
    except ImportError:
        print(f"\nError: {message}", file=sys.stderr)
        if suggestion:
            print(f"Suggestion: {suggestion}", file=sys.stderr)
        print(file=sys.stderr)


def _format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs:.0f}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m {secs:.0f}s"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())
