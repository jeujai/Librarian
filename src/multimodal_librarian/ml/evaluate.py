"""
CLI for before/after model evaluation.

Entry point::

    python -m multimodal_librarian.ml.evaluate \\
        --eval-set <path> --base-model <name> --finetuned-model <name>

Accepts CLI arguments for output directory and report format options.
Displays a progress bar with current step / elapsed time / ETA using
``rich``, and provides descriptive error messages with corrective
suggestions on failure.

Requirements: 10.3, 10.4, 10.5
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ComparisonReport

logger = logging.getLogger(__name__)


class _VerifyFailed(Exception):
    """Internal marker so the outer handler can distinguish a DeepSeek
    ``verify_available`` failure from a failure inside
    ``EvaluationRunner.evaluate``.

    The CLI collapses those two stages into a single ``asyncio.run(_run())``
    call (so the cached ``httpx.AsyncClient`` in ``DeepSeekAIService`` is
    never shared across event loops). Raising this tagged exception from
    inside ``_run`` lets the outer ``except`` ladder preserve the distinct
    error message each stage used to produce.
    """


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser for evaluation."""
    parser = argparse.ArgumentParser(
        prog="python -m multimodal_librarian.ml.evaluate",
        description=(
            "Evaluate a fine-tuned model against a base model by "
            "scoring both on a curated medical question set with "
            "RAG-generated gold answers."
        ),
    )

    # Required
    parser.add_argument(
        "--eval-set",
        type=str,
        required=True,
        help="Path to the evaluation set JSONL file.",
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="llama3.2:3b",
        help=(
            "Ollama model name for the base model "
            "(default: llama3.2:3b)."
        ),
    )
    parser.add_argument(
        "--finetuned-model",
        type=str,
        default="librarian-medical-3b",
        help=(
            "Ollama model name for the fine-tuned model "
            "(default: librarian-medical-3b)."
        ),
    )

    # Output
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./evaluation",
        help="Directory for evaluation reports (default: ./evaluation).",
    )

    # Judge settings
    parser.add_argument(
        "--judge-temperature",
        type=float,
        default=0.1,
        help=(
            "Sampling temperature for the LLM judge "
            "(default: 0.1). Lower values increase scoring "
            "consistency."
        ),
    )
    parser.add_argument(
        "--judge-retries",
        type=int,
        default=2,
        help=(
            "Number of additional retry attempts when the "
            "judge response cannot be parsed (default: 2, "
            "so up to 3 total attempts)."
        ),
    )
    parser.add_argument(
        "--improvement-threshold",
        type=float,
        default=0.05,
        help=(
            "Minimum improvement delta to avoid flagging "
            "(default: 0.05 = 5%%)."
        ),
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the evaluation CLI.

    Returns 0 on success, 1 on failure.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # ------------------------------------------------------------------
    # Validate eval set path early
    # ------------------------------------------------------------------
    eval_set_path = Path(args.eval_set)
    if not eval_set_path.exists():
        _print_error(
            f"Evaluation set not found: {eval_set_path}",
            suggestion=(
                "Generate an evaluation set first using the training "
                "data generation pipeline, or provide a valid path to "
                "an existing evaluation JSONL file."
            ),
        )
        return 1

    if not eval_set_path.is_file():
        _print_error(
            f"Evaluation set path is not a file: {eval_set_path}",
            suggestion="Provide a path to a JSONL file, not a directory.",
        )
        return 1

    # ------------------------------------------------------------------
    # Build EvaluationConfig from CLI args
    # ------------------------------------------------------------------
    from .models import EvaluationConfig

    config = EvaluationConfig(
        eval_set_path=str(eval_set_path),
        base_model=args.base_model,
        finetuned_model=args.finetuned_model,
        output_dir=args.output_dir,
        improvement_threshold=args.improvement_threshold,
    )

    # ------------------------------------------------------------------
    # Instantiate DeepSeek → JudgeService → EvaluationRunner
    # ------------------------------------------------------------------
    try:
        from multimodal_librarian.services.deepseek_ai_service import DeepSeekAIService

        from .judge_service import JudgeService

        deepseek_service = DeepSeekAIService()
        judge_service = JudgeService(
            deepseek_service=deepseek_service,
            max_retries=args.judge_retries,
            temperature=args.judge_temperature,
        )
    except RuntimeError as exc:
        _print_error(
            str(exc),
            suggestion=(
                "Ensure the DEEPSEEK_API_KEY environment variable is set."
            ),
        )
        return 1

    # ------------------------------------------------------------------
    # Run evaluation with rich progress display
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
        "\n[bold cyan]Model Evaluation[/bold cyan]",
    )
    console.print(f"  Eval set:        {config.eval_set_path}")
    console.print(f"  Base model:      {config.base_model}")
    console.print(f"  Fine-tuned:      {config.finetuned_model}")
    console.print(f"  Output:          {config.output_dir}")
    console.print(f"  Judge temp:      {args.judge_temperature}")
    console.print(f"  Judge retries:   {args.judge_retries}")
    console.print(f"  Threshold:       {config.improvement_threshold:.0%}")
    console.print()

    # Verify DeepSeek is reachable before processing any questions, then
    # run the evaluation — both inside a single ``asyncio.run`` so the
    # cached ``httpx.AsyncClient`` on ``DeepSeekAIService`` is never
    # shared across event loops (Track B structural fix for
    # ``Event loop is closed``).
    console.print("[dim]Verifying DeepSeek API availability...[/dim]")

    from .evaluation_runner import EvaluationRunner

    runner = EvaluationRunner(config, judge=judge_service)

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    start_time = time.monotonic()
    task_id = None

    def _progress_callback(current: int, total: int) -> None:
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(
                "[cyan]Evaluating questions", total=total
            )
        progress.update(task_id, completed=current)

    async def _run() -> "ComparisonReport":
        # Verify stage — tag its failures so the outer handler can
        # render the same error message it used before the collapse.
        try:
            await judge_service.verify_available()
        except RuntimeError as exc:
            raise _VerifyFailed(str(exc)) from exc
        console.print("[green]DeepSeek API is available.[/green]\n")

        # Evaluate stage — runs in the same event loop so the cached
        # DeepSeek client, whatever loop it was bound to, is still valid.
        return await runner.evaluate(
            eval_set_path=eval_set_path,
            base_model=config.base_model,
            finetuned_model=config.finetuned_model,
            progress_callback=_progress_callback,
        )

    try:
        with progress:
            report = asyncio.run(_run())
    except _VerifyFailed as exc:
        _print_error(
            f"DeepSeek API is unreachable: {exc}",
            suggestion=(
                "Check your DEEPSEEK_API_KEY, network connectivity, "
                "and the DeepSeek API status."
            ),
        )
        return 1
    except ValueError as exc:
        _print_error(str(exc))
        return 1
    except RuntimeError as exc:
        _print_error(str(exc))
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Evaluation interrupted by user.[/yellow]")
        return 1

    # ------------------------------------------------------------------
    # Print summary
    # ------------------------------------------------------------------
    elapsed = time.monotonic() - start_time
    console.print()
    console.print("[bold green]Evaluation complete![/bold green]")
    console.print(f"  Total time:          {_format_duration(elapsed)}")
    console.print(f"  Questions evaluated: {len(report.results)}")

    # Similarity scores (embedding-based)
    if report.base_mean_similarity > 0:
        console.print(
            f"  Base mean sim:       "
            f"[bold]{report.base_mean_similarity:.4f}[/bold]"
        )
        console.print(
            f"  Fine-tuned mean sim: "
            f"[bold]{report.finetuned_mean_similarity:.4f}[/bold]"
        )
        sim_d = report.similarity_delta
        if sim_d > 0:
            sim_str = f"[green]+{sim_d:.4f}[/green]"
        elif sim_d < 0:
            sim_str = f"[red]{sim_d:.4f}[/red]"
        else:
            sim_str = f"{sim_d:.4f}"
        console.print(f"  Improvement delta:   {sim_str}")

    # Judge scores
    console.print(f"  Win rate:            {report.win_rate:.4f}")
    console.print(f"  Mean score delta:    {report.mean_score_delta:.4f}")

    # Color the delta based on improvement
    delta = report.improvement_delta
    if delta >= config.improvement_threshold:
        delta_str = f"[green]+{delta:.4f}[/green]"
    elif delta > 0:
        delta_str = f"[yellow]+{delta:.4f}[/yellow]"
    else:
        delta_str = f"[red]{delta:.4f}[/red]"
    console.print(f"  Judge delta:         {delta_str}")

    # Per-dimension scores
    if report.base_mean_scores and report.finetuned_mean_scores:
        console.print()
        console.print("[bold]Per-Dimension Scores:[/bold]")
        for dim in [
            "factual_accuracy",
            "completeness",
            "clinical_relevance",
            "coherence",
        ]:
            base_val = report.base_mean_scores.get(dim, 0.0)
            ft_val = report.finetuned_mean_scores.get(dim, 0.0)
            dim_delta = ft_val - base_val
            dim_label = dim.replace("_", " ").title()
            color = (
                "green" if dim_delta > 0
                else ("yellow" if dim_delta == 0 else "red")
            )
            console.print(
                f"  {dim_label}: "
                f"base={base_val:.2f}  ft={ft_val:.2f}  "
                f"[{color}]delta={dim_delta:+.2f}[/{color}]"
            )

    # Judge stats
    if report.judge_stats:
        console.print()
        console.print("[bold]Judge Stats:[/bold]")
        js = report.judge_stats
        console.print(
            f"  Successful: {js.get('successful_judgments', 0)}"
            f"  Failed: {js.get('failed_judgments', 0)}"
            f"  Total: {js.get('total_questions', 0)}"
        )

    if report.flagged:
        console.print()
        console.print(
            "[bold yellow]⚠ Improvement below threshold[/bold yellow]"
        )
        for rec in report.recommendations:
            console.print(f"  [yellow]• {rec}[/yellow]")

    # Show semantic type breakdown
    if report.by_semantic_type:
        console.print()
        console.print("[bold]Results by Semantic Type:[/bold]")
        for stype, metrics in sorted(report.by_semantic_type.items()):
            wr = metrics.get("win_rate", 0)
            msd = metrics.get("mean_score_delta", 0)
            color = "green" if wr > 0.5 else ("yellow" if wr == 0.5 else "red")
            console.print(
                f"  {stype}: "
                f"win_rate={wr:.4f} "
                f"[{color}]score_delta={msd:+.4f}[/{color}]"
            )

    # Show similarity by semantic type
    if report.similarity_by_semantic_type:
        console.print()
        console.print("[bold]Similarity by Semantic Type:[/bold]")
        for stype, metrics in sorted(
            report.similarity_by_semantic_type.items()
        ):
            b_sim = metrics.get("base_mean_sim", 0)
            ft_sim = metrics.get("finetuned_mean_sim", 0)
            s_delta = metrics.get("delta", 0)
            color = (
                "green" if s_delta > 0
                else ("yellow" if s_delta == 0 else "red")
            )
            console.print(
                f"  {stype}: "
                f"base={b_sim:.4f} ft={ft_sim:.4f} "
                f"[{color}]delta={s_delta:+.4f}[/{color}]"
            )

    output_dir = Path(config.output_dir)
    console.print()
    console.print(f"[dim]Reports saved to {output_dir}/[/dim]")
    console.print(
        f"[dim]  JSON:     {output_dir / 'comparison_report.json'}[/dim]"
    )
    console.print(
        f"[dim]  Markdown: {output_dir / 'comparison_report.md'}[/dim]"
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
