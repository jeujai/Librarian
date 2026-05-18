#!/usr/bin/env python3
"""
End-to-end Medical Knowledge Fine-Tuning Pipeline.

Orchestrates all 7 steps of the training pipeline:

  Phase 1 — Training Data Generation (Docker stack)
    Step 1: Trigger data generation via POST /api/v1/ml/training-data/generate
    Step 2: Poll for completion via GET /api/v1/ml/training-data/status/{job_id}
    Step 3: Download the dataset via GET /api/v1/ml/training-data/download/{job_id}

  Phase 2 — Fine-Tuning (Host machine, Metal GPU)
    Step 4: QLoRA fine-tuning via mlx-lm

  Phase 3 — Export (Host machine)
    Step 5: GGUF export + Ollama registration

  Phase 4 — Evaluation (Host machine)
    Step 6: (Eval set produced with step 3)
    Step 7: Before/after evaluation via Ollama

Usage:
    # Full pipeline with defaults
    python scripts/run-training-pipeline.py

    # Custom pair count and strategies
    python scripts/run-training-pipeline.py --pair-count 5000 --strategies kg umls_reasoning

    # Resume from fine-tuning (skip data generation)
    python scripts/run-training-pipeline.py --start-from finetune --dataset ./training_runs/.../training_data.jsonl

    # Resume from export
    python scripts/run-training-pipeline.py --start-from export --adapter ./training_runs/.../adapters

    # Resume from evaluation
    python scripts/run-training-pipeline.py --start-from evaluate --eval-set ./training_runs/.../eval_set.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import requests

# Load .env file if present (for DEEPSEEK_API_KEY and other secrets)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed — fall back to manual .env loading
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        with open(_env_path) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _key, _, _val = _line.partition("=")
                    os.environ.setdefault(_key.strip(), _val.strip())

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_BASE_URL = "http://localhost:8000"
API_PREFIX = "/api/v1/ml/training-data"
POLL_INTERVAL_SECONDS = 10
MAX_POLL_MINUTES = 2100  # 35 hours soft timeout for data generation

STEPS = ["generate", "finetune", "export", "evaluate"]
TRAINING_RUNS_DIR = Path("training_runs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _log_phase(phase: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {phase}")
    print("=" * width)
    print(flush=True)


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = int(minutes // 60)
    mins = minutes % 60
    return f"{hours}h {mins}m {secs}s"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _check_docker_health() -> bool:
    """Verify the app container is healthy."""
    try:
        r = requests.get(f"{APP_BASE_URL}/health/simple", timeout=5)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


def _check_ollama_available() -> bool:
    """Check if Ollama is running on the host."""
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


def _run_host_command(cmd: list[str], description: str) -> int:
    """Run a command on the host, streaming output. Returns exit code."""
    _log(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=str(Path.cwd()))
        return result.returncode
    except FileNotFoundError:
        _log(f"ERROR: Command not found: {cmd[0]}")
        _log(f"  Ensure the required tool is installed for: {description}")
        return 1
    except KeyboardInterrupt:
        _log("Interrupted by user.")
        return 130


# ---------------------------------------------------------------------------
# Partial data helpers (resume support)
# ---------------------------------------------------------------------------

# Maps strategy name → partial file name (mirrors server-side convention)
_STRATEGY_TO_PARTIAL_FILE: dict[str, str] = {
    "kg": "partial_kg.jsonl",
    "rag": "partial_rag.jsonl",
    "umls_reasoning": "partial_umls.jsonl",
}


def _download_partial_data(
    job_id: str,
    run_dir: Path,
    strategies: list[str],
) -> dict[str, int]:
    """Download partial JSONL files from the server after a failed job.

    Hits GET /download-partial/{job_id} to discover available partial files,
    then downloads each one to *run_dir*.

    Returns a dict mapping strategy name → pair count for successfully
    downloaded files.  Never raises — download failures are logged as
    warnings so the pipeline can continue.

    Requirements: 1.1, 1.2, 1.3, 1.4
    """
    recovered: dict[str, int] = {}

    # Step 1: discover which partial files the server has
    try:
        r = requests.get(
            f"{APP_BASE_URL}{API_PREFIX}/download-partial/{job_id}",
            timeout=30,
        )
    except requests.ConnectionError as exc:
        _log(f"Warning: Could not reach partial-data endpoint: {exc}")
        return recovered

    if r.status_code == 404:
        _log("No partial data available on the server for this job.")
        return recovered

    if r.status_code != 200:
        _log(f"Warning: partial-data listing returned {r.status_code}: {r.text}")
        return recovered

    listing = r.json()
    partial_files = listing.get("partial_files", {})

    if not partial_files:
        _log("Server reports no partial files for this job.")
        return recovered

    # Step 2: download each available strategy file
    for strategy, info in partial_files.items():
        if strategy not in _STRATEGY_TO_PARTIAL_FILE:
            continue

        filename = _STRATEGY_TO_PARTIAL_FILE[strategy]
        dest = run_dir / filename

        try:
            r = requests.get(
                f"{APP_BASE_URL}{API_PREFIX}/download-partial/{job_id}",
                params={"strategy": strategy},
                timeout=60,
                stream=True,
            )
        except requests.ConnectionError as exc:
            _log(f"Warning: Could not download partial data for '{strategy}': {exc}")
            continue

        if r.status_code != 200:
            _log(f"Warning: download-partial for '{strategy}' returned {r.status_code}")
            continue

        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        pair_count = info.get("pair_count", sum(1 for _ in open(dest)))
        recovered[strategy] = pair_count
        _log(f"  Recovered {pair_count} pairs for strategy '{strategy}' → {dest}")

    if recovered:
        total = sum(recovered.values())
        _log(f"Total recovered: {total} pairs across {len(recovered)} strategy(ies).")
    else:
        _log("No partial data files could be downloaded.")

    return recovered


# Required fields for a valid InstructionTuningPair JSON object.
_REQUIRED_PAIR_FIELDS = {"instruction", "context", "response", "metadata"}
_REQUIRED_METADATA_FIELDS = {"strategy", "confidence_score"}


def _scan_partial_data(run_dir: Path) -> dict[str, dict]:
    """Scan a directory for partial JSONL files and validate their contents.

    Reads ``partial_kg.jsonl``, ``partial_rag.jsonl``, and
    ``partial_umls.jsonl`` from *run_dir*.  Each line is parsed as JSON
    and validated to contain the required ``InstructionTuningPair``
    fields.  Invalid lines are skipped with a warning.

    Returns a dict mapping strategy name → ``{path, pair_count, pairs}``
    where *pairs* is a list of validated JSON dicts.

    Requirements: 5.2, 5.3, 7.1, 7.2, 7.4
    """
    result: dict[str, dict] = {}

    for strategy, filename in _STRATEGY_TO_PARTIAL_FILE.items():
        filepath = run_dir / filename
        if not filepath.exists():
            continue

        valid_pairs: list[dict] = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    _log(f"Warning: {filename}:{line_num} — empty line, skipping.")
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as exc:
                    _log(f"Warning: {filename}:{line_num} — malformed JSON ({exc}), skipping.")
                    continue

                # Validate required top-level fields
                if not isinstance(obj, dict):
                    _log(f"Warning: {filename}:{line_num} — not a JSON object, skipping.")
                    continue

                missing = _REQUIRED_PAIR_FIELDS - obj.keys()
                if missing:
                    _log(f"Warning: {filename}:{line_num} — missing fields {missing}, skipping.")
                    continue

                # Validate required metadata fields
                meta = obj.get("metadata")
                if not isinstance(meta, dict):
                    _log(f"Warning: {filename}:{line_num} — metadata is not an object, skipping.")
                    continue

                missing_meta = _REQUIRED_METADATA_FIELDS - meta.keys()
                if missing_meta:
                    _log(f"Warning: {filename}:{line_num} — metadata missing {missing_meta}, skipping.")
                    continue

                # Validate non-empty string fields
                if not all(isinstance(obj.get(f), str) and obj[f].strip()
                           for f in ("instruction", "context", "response")):
                    _log(f"Warning: {filename}:{line_num} — empty or non-string text field, skipping.")
                    continue

                valid_pairs.append(obj)

        pair_count = len(valid_pairs)
        _log(f"Loaded {pair_count} valid pairs from {filepath}")
        result[strategy] = {
            "path": filepath,
            "pair_count": pair_count,
            "pairs": valid_pairs,
        }

    if not result:
        _log("Warning: No partial data files found in the resume directory.")

    return result


def _upload_partial_data(job_id: str, partial_data: dict[str, dict]) -> bool:
    """Upload partial JSONL files to the server for a resumed job.

    Uploads each partial file via ``POST /upload-partial/{job_id}``.
    Returns True if all uploads succeed, False otherwise.  Failures are
    logged as warnings — the caller decides whether to proceed.

    Requirements: 5.4
    """
    all_ok = True

    for strategy, info in partial_data.items():
        filepath: Path = info["path"]
        try:
            with open(filepath, "rb") as f:
                r = requests.post(
                    f"{APP_BASE_URL}{API_PREFIX}/upload-partial/{job_id}",
                    files={"file": (filepath.name, f, "application/jsonl")},
                    data={"strategy": strategy},
                    timeout=120,
                )
        except requests.ConnectionError as exc:
            _log(f"Warning: Could not upload partial data for '{strategy}': {exc}")
            all_ok = False
            continue

        if r.status_code != 200:
            _log(f"Warning: upload-partial for '{strategy}' returned {r.status_code}: {r.text}")
            all_ok = False
            continue

        _log(f"  Uploaded partial data for '{strategy}' ({info['pair_count']} pairs)")

    return all_ok


def _load_saved_config(run_dir: Path) -> Optional[dict]:
    """Read ``pipeline_config.json`` from a previous Run_Directory.

    Returns the parsed dict on success, or ``None`` if the file is
    missing or contains invalid JSON.

    Requirements: 8.1, 8.4, 8.5
    """
    config_path = run_dir / "pipeline_config.json"

    if not config_path.exists():
        _log(f"Warning: No pipeline_config.json found in {run_dir}. "
             "Using standard CLI defaults.")
        return None

    try:
        text = config_path.read_text(encoding="utf-8")
        return json.loads(text)
    except json.JSONDecodeError as exc:
        _log(f"Warning: pipeline_config.json contains invalid JSON ({exc}). "
             "Using standard CLI defaults.")
        return None
    except OSError as exc:
        _log(f"Warning: Could not read pipeline_config.json ({exc}). "
             "Using standard CLI defaults.")
        return None


def _apply_saved_config(
    args: argparse.Namespace,
    saved_config: dict,
    explicit_args: set[str],
) -> argparse.Namespace:
    """Merge saved config values into *args* as defaults.

    For each key in *saved_config* that is **not** in *explicit_args*,
    the corresponding attribute on *args* is overwritten with the saved
    value.  Explicitly provided CLI arguments always take precedence.

    Returns the (mutated) *args* namespace.

    Requirements: 8.2, 8.3, 8.6
    """
    restored: list[str] = []

    for key, value in saved_config.items():
        # Skip internal / non-argument keys
        if not hasattr(args, key):
            continue
        # Explicit CLI args always win
        if key in explicit_args:
            continue
        setattr(args, key, value)
        restored.append(key)

    if restored:
        _log(f"Restored {len(restored)} parameter(s) from saved config: "
             f"{', '.join(sorted(restored))}")
    else:
        _log("No parameters restored from saved config (all were explicitly provided).")

    return args


# ---------------------------------------------------------------------------
# Step 1–3: Training Data Generation (Docker)
# ---------------------------------------------------------------------------


def step_generate(
    run_dir: Path,
    pair_count: int,
    strategies: list[str],
    random_seed: int,
    min_confidence: float,
    similarity_threshold: float = 0.90,
    semantic_types: Optional[list[str]] = None,
    resume_from: Optional[Path] = None,
) -> Optional[tuple[Path, Optional[Path]]]:
    """Trigger data generation, poll, and download the dataset.

    When *resume_from* is provided, scans the directory for partial data
    files, uploads them to the server, and includes a ``resume_data``
    manifest in the generation request so the server can skip
    already-completed strategies.

    Returns a tuple of (dataset_path, eval_set_path), or None on failure.
    """
    _log_phase("Phase 1: Training Data Generation (Docker)")

    # --- Resume: scan and prepare partial data ---
    partial_data: dict[str, dict] = {}
    resume_manifest: Optional[dict] = None

    if resume_from is not None:
        _log(f"Resuming from: {resume_from}")
        partial_data = _scan_partial_data(resume_from)
        if partial_data:
            # Build the ResumeManifest payload
            resume_manifest = {
                "strategies": {
                    strategy: {
                        "pair_count": info["pair_count"],
                        "complete": True,
                    }
                    for strategy, info in partial_data.items()
                }
            }
            _log(f"Resume manifest: {json.dumps(resume_manifest, indent=2)}")
        else:
            _log("Warning: No partial data found in resume directory. "
                 "Proceeding with fresh generation.")

    # --- Pre-flight check ---
    _log("Checking Docker stack health...")
    if not _check_docker_health():
        _log("ERROR: App container is not healthy at " + APP_BASE_URL)
        _log("  Run 'docker compose up -d' and wait for health checks.")
        return None
    _log("Docker stack is healthy.")

    # --- Step 1: Trigger generation ---
    _log(f"Step 1: Triggering data generation ({pair_count} pairs, "
         f"strategies={strategies}, seed={random_seed})...")

    payload = {
        "target_pair_count": pair_count,
        "strategies": strategies,
        "random_seed": random_seed,
        "min_confidence_score": min_confidence,
        "similarity_threshold": similarity_threshold,
    }

    # Include semantic_types in the API payload for generation-time filtering
    if semantic_types:
        payload["semantic_types"] = semantic_types

    # Include resume_data in the payload when resuming
    if resume_manifest:
        payload["resume_data"] = resume_manifest

    # --- Upload partial data BEFORE triggering generation ---
    # The Celery task loads pre-existing pairs from the job's output
    # directory at startup, so the files must be on the server before
    # the task is dispatched.
    job_id: Optional[str] = None
    if partial_data:
        job_id = str(uuid4())
        _log(f"Pre-allocated job ID for resume: {job_id}")
        _log("Uploading partial data to server...")
        upload_ok = _upload_partial_data(job_id, partial_data)
        if not upload_ok:
            _log("Warning: Some partial data uploads failed. "
                 "The server may re-generate those strategies.")
        payload["job_id"] = job_id

    try:
        r = requests.post(
            f"{APP_BASE_URL}{API_PREFIX}/generate",
            json=payload,
            timeout=30,
        )
    except requests.ConnectionError as exc:
        _log(f"ERROR: Could not connect to API: {exc}")
        return None

    if r.status_code != 202:
        _log(f"ERROR: API returned {r.status_code}: {r.text}")
        return None

    resp = r.json()
    job_id = resp["job_id"]
    _log(f"Job started: {job_id}")

    # --- Step 2: Poll for completion ---
    _log("Step 2: Polling for completion...")
    start_time = time.time()
    deadline = start_time + MAX_POLL_MINUTES * 60
    last_phase = ""

    while time.time() < deadline:
        try:
            r = requests.get(
                f"{APP_BASE_URL}{API_PREFIX}/status/{job_id}",
                timeout=10,
            )
        except requests.ConnectionError:
            _log("  Warning: connection lost, retrying in 10s...")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        if r.status_code != 200:
            _log(f"  Warning: status endpoint returned {r.status_code}")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        status_data = r.json()
        job_status = status_data.get("status", "unknown")
        phase = status_data.get("phase", "")
        pct = status_data.get("percentage")
        eta = status_data.get("eta_seconds")
        pairs = status_data.get("pairs_per_strategy", {})

        # Log phase transitions on a new line
        if phase != last_phase:
            if last_phase:
                print()  # End the previous \r line
            last_phase = phase

        # Build single-line progress display
        elapsed = _format_duration(time.time() - start_time)
        pct_str = f"{pct:.1f}%" if pct is not None else "?"
        eta_str = "Done" if pct is not None and pct >= 100.0 else (_format_duration(eta) if eta else "?")
        pairs_str = ", ".join(f"{k}={v}" for k, v in pairs.items()) if pairs else ""

        # Map phase to user-friendly label
        if phase == "rag_rewriting":
            label = "Rewriting"
        elif phase == "rag_generation":
            label = "Generating"
        elif phase == "rag_distilling":
            label = "Distilling"
        else:
            label = phase or "Initializing"

        line = (
            f"  [{label}] {pct_str} | Elapsed: {elapsed} | ETA: {eta_str}"
            + (f" | Pairs: {pairs_str}" if pairs_str else "")
        )
        # Overwrite in place with \r
        print(f"\r{line:<80}", end="", flush=True)

        if job_status == "completed":
            print()  # End the \r line
            _log("Data generation completed!")
            # Log result summary if available
            result = status_data.get("result")
            if result:
                _log(f"  Summary: {json.dumps(result, indent=2)}")
            break

        if job_status == "failed":
            print()  # End the \r line
            error = status_data.get("error", "Unknown error")
            _log(f"ERROR: Data generation failed: {error}")

            # --- Attempt to recover partial data (Req 1.1, 1.5) ---
            _log("Attempting to download partial data...")
            recovered = _download_partial_data(job_id, run_dir, strategies)
            if recovered:
                _log("\nTo resume this run, use:")
                _log(f"  python scripts/run-training-pipeline.py "
                     f"--resume-from {run_dir}")
            return None

        time.sleep(POLL_INTERVAL_SECONDS)
    else:
        _log(f"ERROR: Data generation timed out after {MAX_POLL_MINUTES} minutes.")
        return None

    # --- Step 3: Download dataset ---
    _log("Step 3: Downloading dataset...")
    dataset_path = run_dir / "training_data.jsonl"

    try:
        r = requests.get(
            f"{APP_BASE_URL}{API_PREFIX}/download/{job_id}",
            timeout=60,
            stream=True,
        )
    except requests.ConnectionError as exc:
        _log(f"ERROR: Could not download dataset: {exc}")
        return None

    if r.status_code != 200:
        _log(f"ERROR: Download returned {r.status_code}: {r.text}")
        return None

    with open(dataset_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)

    size_mb = dataset_path.stat().st_size / (1024 * 1024)
    line_count = sum(1 for _ in open(dataset_path))
    _log(f"Dataset saved: {dataset_path} ({size_mb:.1f} MB, {line_count} lines)")

    # --- Step 3a: Post-hoc semantic type filter (legacy) ---
    # When semantic_types is provided, filtering is handled at generation
    # time via the API payload, so this step is skipped.
    # This block is retained only for backward compatibility when the
    # server does not support generation-time semantic_types filtering.

    # --- Step 3b: Download evaluation set ---
    eval_set_path: Optional[Path] = None
    _log("Downloading evaluation set...")
    try:
        r = requests.get(
            f"{APP_BASE_URL}{API_PREFIX}/download-eval/{job_id}",
            timeout=60,
            stream=True,
        )
        if r.status_code == 200:
            eval_set_path = run_dir / "eval_set.jsonl"
            with open(eval_set_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            eval_lines = sum(1 for _ in open(eval_set_path))
            _log(f"Eval set saved: {eval_set_path} ({eval_lines} questions)")
        else:
            _log("No evaluation set available (RAG service may not be active).")
    except requests.ConnectionError:
        _log("Warning: Could not download eval set.")

    return dataset_path, eval_set_path


# ---------------------------------------------------------------------------
# Step 4: QLoRA Fine-Tuning (Host)
# ---------------------------------------------------------------------------


def step_finetune(
    run_dir: Path,
    dataset_path: Path,
    model: str,
    lora_rank: int,
    lora_alpha: int,
    num_layers: int,
    lora_dropout: float,
    mask_prompt: bool,
    distill: bool,
    learning_rate: float,
    batch_size: int,
    grad_accumulation: int,
    epochs: int,
    max_memory_gb: float,
    max_seq_length: int = 4096,
) -> Optional[Path]:
    """Run QLoRA fine-tuning. Returns adapter directory or None."""
    _log_phase("Phase 2: QLoRA Fine-Tuning (Host)")

    adapter_dir = run_dir / "adapters"
    _ensure_dir(adapter_dir)

    cmd = [
        sys.executable, "-m", "multimodal_librarian.ml.finetune",
        "--dataset", str(dataset_path),
        "--model", model,
        "--output-dir", str(adapter_dir),
        "--lora-rank", str(lora_rank),
        "--lora-alpha", str(lora_alpha),
        "--num-layers", str(num_layers),
        "--lora-dropout", str(lora_dropout),
        "--learning-rate", str(learning_rate),
        "--batch-size", str(batch_size),
        "--grad-accumulation-steps", str(grad_accumulation),
        "--epochs", str(epochs),
        "--max-memory-gb", str(max_memory_gb),
        "--max-seq-length", str(max_seq_length),
    ]
    if mask_prompt:
        cmd.append("--mask-prompt")
    if distill:
        cmd.append("--distill")

    start = time.time()
    rc = _run_host_command(cmd, "QLoRA fine-tuning")
    elapsed = _format_duration(time.time() - start)

    if rc != 0:
        _log(f"ERROR: Fine-tuning failed (exit code {rc}) after {elapsed}.")
        return None

    _log(f"Fine-tuning completed in {elapsed}.")
    _log(f"Adapters saved to: {adapter_dir}")
    return adapter_dir


# ---------------------------------------------------------------------------
# Step 5: GGUF Export (Host)
# ---------------------------------------------------------------------------


def step_export(
    run_dir: Path,
    adapter_dir: Path,
    base_model: str,
    model_name: str,
    quantization: str,
) -> Optional[Path]:
    """Export to GGUF and register with Ollama. Returns export dir or None."""
    _log_phase("Phase 3: GGUF Export")

    export_dir = run_dir / "exported_model"
    _ensure_dir(export_dir)

    # Check Ollama availability
    ollama_flag = []
    if not _check_ollama_available():
        _log("Warning: Ollama is not running. GGUF + Modelfile will be "
             "saved but not registered. Start Ollama and register manually.")
        ollama_flag = ["--no-ollama"]

    cmd = [
        sys.executable, "-m", "multimodal_librarian.ml.export",
        "--adapter", str(adapter_dir),
        "--output", str(export_dir),
        "--base-model", base_model,
        "--model-name", model_name,
        "--quantization", quantization,
    ] + ollama_flag

    start = time.time()
    rc = _run_host_command(cmd, "GGUF export")
    elapsed = _format_duration(time.time() - start)

    if rc != 0:
        _log(f"ERROR: Export failed (exit code {rc}) after {elapsed}.")
        return None

    _log(f"Export completed in {elapsed}.")
    _log(f"Exported to: {export_dir}")
    return export_dir


# ---------------------------------------------------------------------------
# Step 7: Evaluation (Host)
# ---------------------------------------------------------------------------


def step_evaluate(
    run_dir: Path,
    eval_set_path: Path,
    base_model_ollama: str,
    finetuned_model_ollama: str,
) -> bool:
    """Run before/after evaluation. Returns True on success."""
    _log_phase("Phase 4: Evaluation")

    eval_output_dir = run_dir / "evaluation"
    _ensure_dir(eval_output_dir)

    if not eval_set_path.exists():
        _log(f"ERROR: Evaluation set not found: {eval_set_path}")
        _log("  The eval set should have been produced during data generation.")
        return False

    # Check Ollama
    if not _check_ollama_available():
        _log("ERROR: Ollama is not running. Evaluation requires both models "
             "to be available via Ollama.")
        _log("  Start Ollama: ollama serve")
        return False

    cmd = [
        sys.executable, "-m", "multimodal_librarian.ml.evaluate",
        "--eval-set", str(eval_set_path),
        "--base-model", base_model_ollama,
        "--finetuned-model", finetuned_model_ollama,
        "--output-dir", str(eval_output_dir),
    ]

    start = time.time()
    rc = _run_host_command(cmd, "Model evaluation")
    elapsed = _format_duration(time.time() - start)

    if rc != 0:
        _log(f"ERROR: Evaluation failed (exit code {rc}) after {elapsed}.")
        return False

    _log(f"Evaluation completed in {elapsed}.")
    _log(f"Reports saved to: {eval_output_dir}")
    return True


# ---------------------------------------------------------------------------
# Cleanup: remove old training runs and Ollama models
# ---------------------------------------------------------------------------


def cmd_cleanup(keep: int, dry_run: bool, remove_ollama: bool) -> int:
    """Remove old training runs, keeping the N most recent.

    Optionally removes fine-tuned models from Ollama that were
    registered by older runs.
    """
    _log_phase("Cleanup: Old Training Runs")

    if not TRAINING_RUNS_DIR.exists():
        _log("No training_runs/ directory found. Nothing to clean.")
        return 0

    # List runs sorted oldest-first by directory name (timestamp-based)
    runs = sorted(
        [d for d in TRAINING_RUNS_DIR.iterdir() if d.is_dir()],
        key=lambda p: p.name,
    )

    if len(runs) <= keep:
        _log(f"Found {len(runs)} run(s), keeping {keep}. Nothing to remove.")
        return 0

    to_remove = runs[: len(runs) - keep]
    to_keep = runs[len(runs) - keep:]

    _log(f"Found {len(runs)} run(s). Removing {len(to_remove)}, keeping {len(to_keep)}.")
    print()

    # Collect Ollama model names from runs being removed
    ollama_models_to_remove: list[str] = []

    total_bytes = 0
    for run_dir in to_remove:
        # Calculate size
        run_size = sum(
            f.stat().st_size for f in run_dir.rglob("*") if f.is_file()
        )
        total_bytes += run_size
        size_str = f"{run_size / (1024 * 1024):.1f} MB"

        # Check for Ollama model name in config
        config_file = run_dir / "pipeline_config.json"
        model_name = None
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text())
                model_name = config.get("model_name")
            except (json.JSONDecodeError, OSError):
                pass

        if model_name and remove_ollama:
            ollama_models_to_remove.append(model_name)

        if dry_run:
            _log(f"  [DRY RUN] Would remove: {run_dir} ({size_str})"
                 + (f" + ollama rm {model_name}" if model_name and remove_ollama else ""))
        else:
            _log(f"  Removing: {run_dir} ({size_str})")
            import shutil
            shutil.rmtree(run_dir)

    # Remove Ollama models
    if remove_ollama and ollama_models_to_remove:
        # Deduplicate and exclude models that are still used by kept runs
        kept_models = set()
        for run_dir in to_keep:
            config_file = run_dir / "pipeline_config.json"
            if config_file.exists():
                try:
                    config = json.loads(config_file.read_text())
                    m = config.get("model_name")
                    if m:
                        kept_models.add(m)
                except (json.JSONDecodeError, OSError):
                    pass

        for model_name in set(ollama_models_to_remove):
            if model_name in kept_models:
                _log(f"  Skipping ollama rm {model_name} (still used by a kept run)")
                continue
            if dry_run:
                _log(f"  [DRY RUN] Would run: ollama rm {model_name}")
            else:
                _log(f"  Running: ollama rm {model_name}")
                subprocess.run(
                    ["ollama", "rm", model_name],
                    capture_output=True,
                )

    total_str = f"{total_bytes / (1024 * 1024):.1f} MB"
    if dry_run:
        _log(f"\n  [DRY RUN] Would free ~{total_str} from training_runs/.")
    else:
        _log(f"\n  Freed ~{total_str} from training_runs/.")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run-training-pipeline",
        description="End-to-end Medical Knowledge Fine-Tuning Pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # -- Resume control --
    parser.add_argument(
        "--start-from",
        choices=STEPS,
        default="generate",
        help=(
            "Resume from a specific step. "
            "Choices: generate, finetune, export, evaluate. "
            "(default: generate)"
        ),
    )
    parser.add_argument(
        "--resume-from",
        type=str,
        default=None,
        help=(
            "Path to a previous Run_Directory containing partial data files. "
            "Resumes a failed generation by uploading partial data and "
            "skipping already-completed strategies."
        ),
    )

    # -- Cleanup mode --
    parser.add_argument(
        "--cleanup",
        action="store_true",
        default=False,
        help="Remove old training runs instead of running the pipeline.",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=2,
        help="Number of most recent runs to keep during cleanup (default: 2).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what cleanup would remove without deleting anything.",
    )
    parser.add_argument(
        "--remove-ollama",
        action="store_true",
        default=False,
        help="Also remove fine-tuned models from Ollama during cleanup.",
    )

    # -- Run directory --
    parser.add_argument(
        "--run-dir",
        type=str,
        default=None,
        help=(
            "Directory for this training run. "
            "Defaults to training_runs/<timestamp>/."
        ),
    )

    # -- Data generation (steps 1–3) --
    gen_group = parser.add_argument_group("Data Generation (Steps 1–3)")
    gen_group.add_argument(
        "--pair-count", type=int, default=7500,
        help="Target number of instruction-tuning pairs (default: 7500).",
    )
    gen_group.add_argument(
        "--strategies", nargs="+", default=["kg", "umls_reasoning"],
        help="Generation strategies (default: kg umls_reasoning). Add 'rag' for RAG strategy (higher cost).",
    )
    gen_group.add_argument(
        "--random-seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42).",
    )
    gen_group.add_argument(
        "--min-confidence", type=float, default=0.80,
        help="Minimum confidence score for included pairs (default: 0.80).",
    )
    gen_group.add_argument(
        "--similarity-threshold", type=float, default=0.90,
        help="Dedup similarity threshold; pairs above this are removed (default: 0.90).",
    )
    gen_group.add_argument(
        "--semantic-types", type=str, nargs="*", default=None,
        help="Filter training data to specific semantic types (e.g., 'Diagnostic Procedure' 'Disease or Syndrome').",
    )
    gen_group.add_argument(
        "--dataset", type=str, default=None,
        help="Path to existing dataset JSONL (required when --start-from finetune).",
    )

    # -- Fine-tuning (step 4) --
    ft_group = parser.add_argument_group("Fine-Tuning (Step 4)")
    ft_group.add_argument(
        "--model", type=str,
        default="mlx-community/Llama-3.2-3B-Instruct-4bit",
        help="Base model for fine-tuning (default: mlx-community/Llama-3.2-3B-Instruct-4bit).",
    )
    ft_group.add_argument(
        "--lora-rank", type=int, default=16,
        help="LoRA rank (default: 16).",
    )
    ft_group.add_argument(
        "--lora-alpha", type=int, default=32,
        help="LoRA alpha (default: 32).",
    )
    ft_group.add_argument(
        "--num-layers", type=int, default=32,
        help="Number of transformer layers to apply LoRA to (default: 32, i.e. all layers).",
    )
    ft_group.add_argument(
        "--lora-dropout", type=float, default=0.0,
        help="LoRA dropout rate (default: 0.0).",
    )
    ft_group.add_argument(
        "--mask-prompt", action="store_true", default=True,
        help="Only train on assistant response tokens, not system/user prompt (default: True).",
    )
    ft_group.add_argument(
        "--no-mask-prompt", action="store_false", dest="mask_prompt",
        help="Train on all tokens including system/user prompt.",
    )
    ft_group.add_argument(
        "--distill", action="store_true", default=False,
        help="Knowledge distillation mode: strip context and citations so the model learns standalone answers.",
    )
    ft_group.add_argument(
        "--learning-rate", type=float, default=1e-4,
        help="Learning rate (default: 1e-4).",
    )
    ft_group.add_argument(
        "--batch-size", type=int, default=4,
        help="Training batch size (default: 4).",
    )
    ft_group.add_argument(
        "--grad-accumulation", type=int, default=4,
        help="Gradient accumulation steps (default: 4).",
    )
    ft_group.add_argument(
        "--epochs", type=int, default=3,
        help="Number of training epochs (default: 3).",
    )
    ft_group.add_argument(
        "--max-memory-gb", type=float, default=28.0,
        help="Max GPU memory before batch size reduction (default: 28.0).",
    )
    ft_group.add_argument(
        "--max-seq-length", type=int, default=4096,
        help="Max sequence length in tokens; longer examples truncated (default: 4096).",
    )

    # -- Export (step 5) --
    exp_group = parser.add_argument_group("Export (Step 5)")
    exp_group.add_argument(
        "--model-name", type=str, default="librarian-medical-3b",
        help="Ollama model name for the fine-tuned model (default: librarian-medical-3b).",
    )
    exp_group.add_argument(
        "--quantization", type=str, default="Q4_K_M",
        choices=["Q4_0", "Q4_K_M", "Q4_K_S", "Q5_0", "Q5_K_M", "Q5_K_S", "Q8_0"],
        help="GGUF quantization level (default: Q4_K_M).",
    )
    exp_group.add_argument(
        "--adapter", type=str, default=None,
        help="Path to existing adapter dir (required when --start-from export).",
    )

    # -- Evaluation (step 7) --
    eval_group = parser.add_argument_group("Evaluation (Step 7)")
    eval_group.add_argument(
        "--base-model-ollama", type=str, default="llama3.2:3b",
        help="Ollama name for the base model (default: llama3.2:3b).",
    )
    eval_group.add_argument(
        "--eval-set", type=str, default=None,
        help="Path to existing eval set JSONL (required when --start-from evaluate).",
    )

    return parser


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # -- Cleanup mode --
    if args.cleanup:
        return cmd_cleanup(
            keep=args.keep,
            dry_run=args.dry_run,
            remove_ollama=args.remove_ollama,
        )

    # -- Determine which CLI args were explicitly provided --
    # Compare parsed values against parser defaults to detect explicit args.
    # This is needed so _apply_saved_config() knows which args to preserve.
    defaults = {k: v for k, v in vars(parser.parse_args([])).items()}
    explicit_args: set[str] = set()
    for key, value in vars(args).items():
        if key in defaults and value != defaults[key]:
            explicit_args.add(key)

    # -- Restore saved config when resuming --
    resume_from: Optional[Path] = None
    if args.resume_from:
        resume_from = Path(args.resume_from)
        if not resume_from.is_dir():
            _log(f"ERROR: --resume-from directory does not exist: {resume_from}")
            return 1

        saved_config = _load_saved_config(resume_from)
        if saved_config is not None:
            args = _apply_saved_config(args, saved_config, explicit_args)

    # -- Determine run directory --
    if args.run_dir:
        run_dir = Path(args.run_dir)
    elif resume_from is not None:
        # Reuse the resumed run's directory (Req 5.5)
        run_dir = resume_from
    else:
        run_dir = Path("training_runs") / _timestamp()
    _ensure_dir(run_dir)

    # Save the full config for reproducibility
    config_path = run_dir / "pipeline_config.json"
    config_path.write_text(json.dumps(vars(args), indent=2, default=str))

    start_idx = STEPS.index(args.start_from)
    pipeline_start = time.time()

    _log_phase("Medical Knowledge Fine-Tuning Pipeline")
    _log(f"Run directory: {run_dir}")
    _log(f"Starting from: {args.start_from}")
    print()

    # Track artifacts across steps
    dataset_path: Optional[Path] = None
    adapter_dir: Optional[Path] = None
    eval_set_path: Optional[Path] = None

    # Resolve pre-existing artifacts for resume
    if args.dataset:
        dataset_path = Path(args.dataset)
    if args.adapter:
        adapter_dir = Path(args.adapter)
    if args.eval_set:
        eval_set_path = Path(args.eval_set)

    # ---------------------------------------------------------------
    # Step 1–3: Data Generation
    # ---------------------------------------------------------------
    if start_idx <= STEPS.index("generate"):
        gen_result = step_generate(
            run_dir=run_dir,
            pair_count=args.pair_count,
            strategies=args.strategies,
            random_seed=args.random_seed,
            min_confidence=args.min_confidence,
            similarity_threshold=args.similarity_threshold,
            semantic_types=args.semantic_types,
            resume_from=resume_from,
        )
        if gen_result is None:
            _log("Pipeline aborted at data generation.")
            _log(f"To resume: python scripts/run-training-pipeline.py "
                 f"--start-from finetune --dataset <path> --run-dir {run_dir}")
            return 1

        dataset_path, generated_eval_path = gen_result
        if dataset_path is None:
            _log("Pipeline aborted at data generation.")
            return 1
        if generated_eval_path is not None:
            eval_set_path = generated_eval_path

    # ---------------------------------------------------------------
    # Step 4: Fine-Tuning
    # ---------------------------------------------------------------
    if start_idx <= STEPS.index("finetune"):
        if dataset_path is None:
            _log("ERROR: No dataset available for fine-tuning.")
            _log("  Provide --dataset <path> when using --start-from finetune.")
            return 1

        if not dataset_path.exists():
            _log(f"ERROR: Dataset not found: {dataset_path}")
            return 1

        adapter_dir = step_finetune(
            run_dir=run_dir,
            dataset_path=dataset_path,
            model=args.model,
            lora_rank=args.lora_rank,
            lora_alpha=args.lora_alpha,
            num_layers=args.num_layers,
            lora_dropout=args.lora_dropout,
            mask_prompt=args.mask_prompt,
            distill=args.distill,
            learning_rate=args.learning_rate,
            batch_size=args.batch_size,
            grad_accumulation=args.grad_accumulation,
            epochs=args.epochs,
            max_memory_gb=args.max_memory_gb,
            max_seq_length=args.max_seq_length,
        )
        if adapter_dir is None:
            _log("Pipeline aborted at fine-tuning.")
            _log(f"To resume: python scripts/run-training-pipeline.py "
                 f"--start-from finetune --dataset {dataset_path} "
                 f"--run-dir {run_dir}")
            return 1

    # ---------------------------------------------------------------
    # Step 5: Export
    # ---------------------------------------------------------------
    if start_idx <= STEPS.index("export"):
        if adapter_dir is None:
            _log("ERROR: No adapter directory available for export.")
            _log("  Provide --adapter <path> when using --start-from export.")
            return 1

        if not adapter_dir.exists():
            _log(f"ERROR: Adapter directory not found: {adapter_dir}")
            return 1

        export_dir = step_export(
            run_dir=run_dir,
            adapter_dir=adapter_dir,
            base_model=args.model,
            model_name=args.model_name,
            quantization=args.quantization,
        )
        if export_dir is None:
            _log("Pipeline aborted at export.")
            _log(f"To resume: python scripts/run-training-pipeline.py "
                 f"--start-from export --adapter {adapter_dir} "
                 f"--run-dir {run_dir}")
            return 1

    # ---------------------------------------------------------------
    # Step 7: Evaluation
    # ---------------------------------------------------------------
    if start_idx <= STEPS.index("evaluate"):
        # Try to find eval set if not explicitly provided
        if eval_set_path is None:
            candidates = [
                run_dir / "eval_set.jsonl",
                run_dir / "evaluation_set.jsonl",
            ]
            for c in candidates:
                if c.exists():
                    eval_set_path = c
                    break

        if eval_set_path is None or not eval_set_path.exists():
            _log("WARNING: No evaluation set found. Skipping evaluation.")
            _log("  To run evaluation later:")
            _log(f"    python scripts/run-training-pipeline.py "
                 f"--start-from evaluate --eval-set <path> "
                 f"--run-dir {run_dir}")
        else:
            ok = step_evaluate(
                run_dir=run_dir,
                eval_set_path=eval_set_path,
                base_model_ollama=args.base_model_ollama,
                finetuned_model_ollama=args.model_name,
            )
            if not ok:
                _log("Pipeline completed with evaluation failure.")
                _log(f"To retry evaluation: python scripts/run-training-pipeline.py "
                     f"--start-from evaluate --eval-set {eval_set_path} "
                     f"--run-dir {run_dir}")
                return 1

    # ---------------------------------------------------------------
    # Done
    # ---------------------------------------------------------------
    total_time = _format_duration(time.time() - pipeline_start)

    _log_phase("Pipeline Complete")
    _log(f"Total time: {total_time}")
    _log(f"Run directory: {run_dir}")
    _log("Artifacts:")
    if dataset_path and dataset_path.exists():
        _log(f"  Dataset:    {dataset_path}")
    if adapter_dir and adapter_dir.exists():
        _log(f"  Adapters:   {adapter_dir}")
    export_dir = run_dir / "exported_model"
    if export_dir.exists():
        _log(f"  Export:     {export_dir}")
    eval_dir = run_dir / "evaluation"
    if eval_dir.exists():
        _log(f"  Evaluation: {eval_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
