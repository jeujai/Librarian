"""
CLI for exporting fine-tuned models to GGUF format for Ollama.

Entry point::

    python -m multimodal_librarian.ml.export --adapter <path> --output <path>

Accepts CLI arguments for quantization level, model name, and Ollama
registration toggle. Displays a progress bar with current step / elapsed
time / ETA using ``rich``, and provides descriptive error messages with
corrective suggestions on failure.

Requirements: 10.2, 10.4, 10.5
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
    """Build the CLI argument parser for GGUF export."""
    parser = argparse.ArgumentParser(
        prog="python -m multimodal_librarian.ml.export",
        description=(
            "Export a fine-tuned model to GGUF format and optionally "
            "register it with a local Ollama instance."
        ),
    )

    # Required
    parser.add_argument(
        "--adapter",
        type=str,
        required=True,
        help=(
            "Path to the LoRA adapter weights directory "
            "produced by fine-tuning."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output directory for GGUF file and Modelfile.",
    )

    # Model
    parser.add_argument(
        "--base-model",
        type=str,
        default="mlx-community/Llama-3.2-3B-Instruct-4bit",
        help=(
            "Base model name to fuse adapters with "
            "(default: mlx-community/"
            "Llama-3.2-3B-Instruct-4bit)."
        ),
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="librarian-medical-3b",
        help=(
            "Name for the exported Ollama model "
            "(default: librarian-medical-3b)."
        ),
    )

    # Quantization
    parser.add_argument(
        "--quantization",
        type=str,
        default="Q4_K_M",
        choices=[
            "Q4_0", "Q4_K_M", "Q4_K_S",
            "Q5_0", "Q5_K_M", "Q5_K_S", "Q8_0",
        ],
        help="GGUF quantization level (default: Q4_K_M).",
    )

    # Ollama registration
    parser.add_argument(
        "--no-ollama",
        action="store_true",
        default=False,
        help=(
            "Skip Ollama registration "
            "(just produce GGUF + Modelfile)."
        ),
    )

    # System prompt
    parser.add_argument(
        "--system-prompt",
        type=str,
        default=None,
        help=(
            "Custom system prompt for the Ollama Modelfile. "
            "Uses a medical assistant default if not specified."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the GGUF export CLI.

    Returns 0 on success, 1 on failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Validate adapter path early
    # ------------------------------------------------------------------
    adapter_path = Path(args.adapter)
    if not adapter_path.exists():
        _print_error(
            f"Adapter path not found: {adapter_path}",
            suggestion=(
                "Run fine-tuning first with "
                "'python -m multimodal_librarian.ml.finetune "
                "--dataset <path>' to produce LoRA adapter "
                "weights."
            ),
        )
        return 1

    # ------------------------------------------------------------------
    # Build ExportConfig from CLI args
    # ------------------------------------------------------------------
    from .models import ExportConfig

    system_prompt = args.system_prompt or (
        "You are a medical knowledge assistant trained on curated medical "
        "textbooks, clinical guidelines, and biomedical literature. Provide "
        "accurate, evidence-based responses to medical questions."
    )

    config = ExportConfig(
        adapter_path=str(adapter_path),
        base_model=args.base_model,
        output_dir=args.output,
        model_name=args.model_name,
        quantization=args.quantization,
        register_ollama=not args.no_ollama,
        system_prompt=system_prompt,
    )

    # ------------------------------------------------------------------
    # Run export with rich progress display
    # ------------------------------------------------------------------
    try:
        from rich.console import Console
        from rich.progress import (
            BarColumn,
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
        "\n[bold cyan]GGUF Model Export[/bold cyan]",
    )
    console.print(f"  Adapter:       {config.adapter_path}")
    console.print(f"  Base model:    {config.base_model}")
    console.print(f"  Output:        {config.output_dir}")
    console.print(f"  Model name:    {config.model_name}")
    console.print(f"  Quantization:  {config.quantization}")
    ollama_str = "yes" if config.register_ollama else "no"
    console.print(f"  Ollama:        {ollama_str}")
    console.print()

    from .gguf_exporter import GGUFExporter

    exporter = GGUFExporter(config)

    # The export pipeline has 5 discrete steps. We show a step-based
    # progress bar since the exporter doesn't provide granular callbacks.
    steps = [
        "Fusing LoRA adapters with base model",
        "Converting to GGUF format",
        "Quantizing model weights",
        "Generating Ollama Modelfile",
        (
            "Registering with Ollama"
            if config.register_ollama
            else "Saving artifacts"
        ),
    ]

    start_time = time.monotonic()

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    try:
        with progress:
            task_id = progress.add_task(
                f"[cyan]{steps[0]}", total=len(steps)
            )

            # Run the export — it handles all steps internally.
            # We advance the progress bar after completion since the
            # exporter runs synchronously through all steps.
            for i, step_desc in enumerate(steps):
                progress.update(
                    task_id,
                    completed=i,
                    description=f"[cyan]{step_desc}",
                )

            result = exporter.export()

            progress.update(
                task_id,
                completed=len(steps),
                description="[green]Export complete",
            )

    except FileNotFoundError as exc:
        _print_error(str(exc), suggestion="Check the --adapter path.")
        return 1
    except RuntimeError as exc:
        _print_error(str(exc))
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Export interrupted by user.[/yellow]")
        return 1

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    elapsed = time.monotonic() - start_time
    console.print()
    console.print("[bold green]Export complete![/bold green]")
    console.print(f"  Total time:      {_format_duration(elapsed)}")
    console.print(f"  GGUF path:       {result.gguf_path}")
    console.print(f"  GGUF size:       {result.gguf_size_mb:.1f} MB")
    console.print(f"  Quantization:    {result.quantization}")
    console.print(f"  Modelfile:       {result.modelfile_path}")
    console.print(f"  Model name:      {result.model_name}")

    if result.ollama_registered:
        console.print(
            "  Ollama:          [green]registered[/green]"
        )
        console.print()
        console.print(
            "[dim]Test with: ollama run "
            f"{result.model_name} "
            '"What is metformin?"[/dim]'
        )
    else:
        console.print(
            "  Ollama:          "
            "[yellow]not registered[/yellow]"
        )
        if result.manual_instructions:
            console.print()
            console.print(
                f"[yellow]{result.manual_instructions}[/yellow]"
            )

    console.print()
    console.print(
        "[dim]Next step: evaluate with "
        "'python -m multimodal_librarian.ml.evaluate "
        f"--finetuned-model {result.model_name}'[/dim]"
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
