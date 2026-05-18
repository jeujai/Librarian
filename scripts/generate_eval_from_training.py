#!/usr/bin/env python3
"""
Generate an eval_set.jsonl by sampling 50 training pairs and rephrasing
the instructions into slightly different questions.

The gold answer is the training pair's response (what the model was
trained to produce). This lets us measure whether the fine-tuned model
can answer questions similar to — but not identical to — its training
data, using similarity scoring.

Usage:
    python scripts/generate_eval_from_training.py \
        --training-data training_runs/2026-05-04_140658/training_data.jsonl \
        --output training_runs/2026-05-04_140658/eval_set_from_training.jsonl \
        --count 50
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Rephrasing strategies (deterministic, no LLM needed)
# ---------------------------------------------------------------------------

_REPHRASE_PREFIXES = [
    "Can you explain",
    "Tell me about",
    "What can you tell me about",
    "I'd like to know about",
    "Could you describe",
    "Please explain",
    "What do we know about",
    "Help me understand",
    "I'm curious about",
    "What information is available on",
]

_QUESTION_STARTERS = [
    ("What is", "Could you explain what"),
    ("What are", "Can you describe"),
    ("How does", "Could you explain how"),
    ("How do", "Can you tell me how"),
    ("What causes", "What are the causes of"),
    ("What side effects", "What adverse effects"),
    ("When would", "In what situations would"),
    ("What can", "What is it that"),
    ("How should", "What is the best way to"),
    ("What conditions", "Which conditions"),
    ("I'm wondering about", "Can you tell me about"),
    ("Can you explain", "What do we know about"),
    ("Tell me about", "I'd like to understand"),
    ("What is the role of", "How does ... function as"),
    ("What are the risks of", "What dangers are associated with"),
]


def _rephrase_question(instruction: str, rng: random.Random) -> str:
    """Rephrase an instruction into a different but semantically
    equivalent question using deterministic string transforms.
    """
    text = instruction.strip()

    # Strategy 1: swap known question starters
    for original, replacement in _QUESTION_STARTERS:
        if text.lower().startswith(original.lower()):
            # Preserve the rest of the sentence
            rest = text[len(original):].strip()
            # Remove leading question mark artifacts
            rest = rest.lstrip("?").strip()
            rephrased = f"{replacement} {rest}"
            # Ensure it ends with ?
            if not rephrased.endswith("?"):
                rephrased += "?"
            return rephrased

    # Strategy 2: if it's a statement/request, reframe as a question
    # "I'm wondering about X" → "What can you tell me about X?"
    if text.lower().startswith("i'm wondering") or text.lower().startswith("i am wondering"):
        # Extract the topic
        match = re.match(r"(?:I'm|I am) wondering (?:about )?(.*)", text, re.IGNORECASE)
        if match:
            topic = match.group(1).rstrip("?.!")
            prefix = rng.choice(_REPHRASE_PREFIXES)
            return f"{prefix} {topic}?"

    # Strategy 3: generic prefix swap
    # Strip any existing question prefix and add a new one
    # Remove common prefixes
    stripped = text
    for prefix in ["Can you explain", "Tell me about", "What can you tell me about",
                   "I'd like to know about", "Could you describe", "Please explain",
                   "What do we know about", "Help me understand", "I'm curious about"]:
        if stripped.lower().startswith(prefix.lower()):
            stripped = stripped[len(prefix):].strip()
            break

    if stripped != text:
        # We successfully stripped a prefix, add a different one
        new_prefix = rng.choice(_REPHRASE_PREFIXES)
        result = f"{new_prefix} {stripped}"
        if not result.endswith("?"):
            result = result.rstrip(".!") + "?"
        return result

    # Strategy 4: fallback — prepend a different framing
    topic = text.rstrip("?.!")
    prefix = rng.choice(_REPHRASE_PREFIXES)
    return f"{prefix} {topic}?"


def _classify_difficulty(question: str) -> str:
    """Simple difficulty classification."""
    q_lower = question.lower()
    reasoning_kw = ["mechanism", "pathophysiology", "how", "why",
                    "relationship", "interaction", "differential", "compared"]
    multi_kw = ["associated with", "commonly", "factors", "complications",
                "treatment options", "conditions"]
    if any(kw in q_lower for kw in reasoning_kw):
        return "reasoning"
    if any(kw in q_lower for kw in multi_kw):
        return "multi-concept"
    return "single-concept"


def _infer_semantic_type(pair: dict) -> str:
    """Infer a semantic type from the training pair content."""
    # Check metadata first
    st = pair.get("metadata", {}).get("semantic_type")
    if st:
        return st

    # Heuristic based on instruction content
    instruction = pair.get("instruction", "").lower()
    response = pair.get("response", "").lower()

    if any(kw in instruction for kw in ["side effect", "prescribed", "drug",
                                         "medication", "dose", "pharmacol"]):
        return "Pharmacologic Substance"
    if any(kw in instruction for kw in ["diagnos", "test", "imaging",
                                         "screening", "biopsy", "lab"]):
        return "Diagnostic Procedure"
    if any(kw in instruction for kw in ["symptom", "sign", "present",
                                         "manifest", "pain", "fever"]):
        return "Sign or Symptom"
    if any(kw in instruction for kw in ["treatment", "therapy", "surgery",
                                         "procedure", "intervention"]):
        return "Therapeutic or Preventive Procedure"
    if any(kw in instruction for kw in ["disease", "syndrome", "disorder",
                                         "condition", "illness"]):
        return "Disease or Syndrome"

    # Default
    return "Disease or Syndrome"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate eval set from training data by rephrasing."
    )
    parser.add_argument(
        "--training-data", type=str, required=True,
        help="Path to training_data.jsonl",
    )
    parser.add_argument(
        "--output", type=str, required=True,
        help="Output path for the eval set JSONL",
    )
    parser.add_argument(
        "--count", type=int, default=50,
        help="Number of eval questions to generate (default: 50)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducibility (default: 42)",
    )
    args = parser.parse_args(argv)

    training_path = Path(args.training_data)
    if not training_path.exists():
        print(f"Error: training data not found: {training_path}", file=sys.stderr)
        return 1

    # Load all training pairs
    pairs = []
    with open(training_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))

    print(f"Loaded {len(pairs)} training pairs from {training_path}")

    if len(pairs) < args.count:
        print(f"Warning: only {len(pairs)} pairs available, "
              f"using all of them instead of {args.count}")
        args.count = len(pairs)

    # Sample
    rng = random.Random(args.seed)
    sampled = rng.sample(pairs, args.count)

    # Generate eval questions
    eval_questions = []
    for pair in sampled:
        original_instruction = pair["instruction"]
        rephrased = _rephrase_question(original_instruction, rng)

        # Use the training response as the gold answer
        gold_answer = pair["response"]

        # Build source citations from metadata
        source_doc = pair.get("metadata", {}).get("source_document", "")
        chunk_ids = pair.get("metadata", {}).get("chunk_ids", [])
        citations = []
        if source_doc and chunk_ids:
            for cid in chunk_ids[:3]:  # limit to 3 citations
                citations.append(f"{source_doc} ({cid})")
        if not citations:
            citations = [source_doc or "training-data-source"]

        semantic_type = _infer_semantic_type(pair)
        difficulty = _classify_difficulty(rephrased)

        # Use the training pair's context as eval context
        context = pair.get("context", "")

        eval_questions.append({
            "question": rephrased,
            "gold_answer": gold_answer,
            "semantic_type": semantic_type,
            "source_citations": citations,
            "difficulty_level": difficulty,
            "context": context,
        })

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for eq in eval_questions:
            f.write(json.dumps(eq, ensure_ascii=False) + "\n")

    # Print summary
    from collections import Counter
    type_dist = Counter(eq["semantic_type"] for eq in eval_questions)
    diff_dist = Counter(eq["difficulty_level"] for eq in eval_questions)

    print(f"\nGenerated {len(eval_questions)} eval questions → {output_path}")
    print(f"\nSemantic type distribution:")
    for t, c in type_dist.most_common():
        print(f"  {t}: {c}")
    print(f"\nDifficulty distribution:")
    for d, c in diff_dist.most_common():
        print(f"  {d}: {c}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
