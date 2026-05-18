#!/usr/bin/env python3
"""
Distill an existing training dataset by rewriting RAG-grounded responses
into standalone authoritative medical prose.

Takes a JSONL file of InstructionTuningPair objects (RAG-generated, with
citations and source references) and produces a new JSONL where each
response has been rewritten via DeepSeek into direct "I know this" voice.

Runs on the host (no Docker needed) so you can distill existing data
without rerunning generation.

Usage:
    python scripts/distill-training-data.py \\
        --input training_runs/2026-05-05_145518/training_data.jsonl \\
        --output training_runs/2026-05-05_145518/training_data_distilled.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

# Load .env so DEEPSEEK_API_KEY is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    _env = Path(__file__).resolve().parent.parent / ".env"
    if _env.exists():
        with open(_env) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m = int(seconds // 60)
    s = int(seconds % 60)
    if m < 60:
        return f"{m}m {s}s"
    h = int(m // 60)
    m = m % 60
    return f"{h}h {m}m"


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Distill RAG responses into standalone medical prose.",
    )
    parser.add_argument(
        "--input", required=True,
        help="Input training_data.jsonl",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output JSONL with distilled responses",
    )
    parser.add_argument(
        "--max-concurrent", type=int, default=4,
        help="Concurrent DeepSeek API calls (default: 4)",
    )
    parser.add_argument(
        "--checkpoint-every", type=int, default=100,
        help="Checkpoint-save frequency in pairs (default: 100)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: Input not found: {input_path}", file=sys.stderr)
        return 1

    # Sanity: we need DEEPSEEK_API_KEY
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("ERROR: DEEPSEEK_API_KEY not set (check .env)", file=sys.stderr)
        return 1

    # Import after .env load
    from multimodal_librarian.ml.models import InstructionTuningPair
    from multimodal_librarian.ml.response_distiller import ResponseDistiller
    from multimodal_librarian.services.deepseek_ai_service import DeepSeekAIService

    # Load pairs
    print(f"Loading pairs from {input_path}...")
    pairs: list[InstructionTuningPair] = []
    with input_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                pairs.append(InstructionTuningPair.from_jsonl_line(line))
            except Exception as exc:
                print(f"  Warning: skipping line {line_num}: {exc}")
    total = len(pairs)
    print(f"Loaded {total} pairs.")

    # Check for existing checkpoint
    start_idx = 0
    distilled_pairs: list[InstructionTuningPair] = []
    if output_path.exists():
        print(f"Found existing output at {output_path} — resuming.")
        with output_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    distilled_pairs.append(
                        InstructionTuningPair.from_jsonl_line(line)
                    )
                except Exception:
                    pass
        start_idx = len(distilled_pairs)
        print(f"Already distilled: {start_idx}/{total}. Resuming...")

    if start_idx >= total:
        print("All pairs already distilled. Nothing to do.")
        return 0

    # Build DeepSeek client + adapter
    ai_service = DeepSeekAIService()
    await ai_service.verify_available()

    class _Adapter:
        """Bridges DeepSeekAIService to the distiller's generate() API."""

        def __init__(self, ai):
            self._ai = ai

        async def generate(self, prompt: str, system_prompt: str = "") -> str:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            response = await self._ai.generate_response(
                messages=messages, temperature=0.3, max_tokens=2048,
            )
            return response.content if hasattr(response, "content") else str(response)

    distiller = ResponseDistiller(
        llm_client=_Adapter(ai_service), max_concurrent=args.max_concurrent,
    )

    # Process in chunks so we can checkpoint
    chunk_size = args.checkpoint_every
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if start_idx > 0 else "w"
    start_time = time.monotonic()

    with output_path.open(mode, encoding="utf-8") as fh:
        for chunk_start in range(start_idx, total, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total)
            chunk = pairs[chunk_start:chunk_end]

            # Distill this chunk
            batch = [
                {"question": p.instruction, "response": p.response}
                for p in chunk
            ]
            distilled = await distiller.distill_batch(batch)

            # Update pairs with distilled responses and write to file
            for pair, d in zip(chunk, distilled):
                pair.response = d["response"]
                fh.write(pair.to_jsonl_line() + "\n")
            fh.flush()

            # Progress
            done = chunk_end
            elapsed = time.monotonic() - start_time
            rate = (done - start_idx) / elapsed if elapsed > 0 else 0
            remaining = (total - done) / rate if rate > 0 else 0
            pct = done / total * 100
            print(
                f"\r[Distilling] {pct:.1f}% ({done}/{total}) | "
                f"Elapsed: {_format_duration(elapsed)} | "
                f"ETA: {_format_duration(remaining)} | "
                f"Success: {distiller.success_count} Fail: {distiller.failure_count}"
                f"{' ' * 10}",
                end="", flush=True,
            )

    print()  # End the \r line
    print(f"\nDistilled {total} pairs → {output_path}")
    print(
        f"Total success: {distiller.success_count}, "
        f"failures: {distiller.failure_count} "
        f"(failures keep original response)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
