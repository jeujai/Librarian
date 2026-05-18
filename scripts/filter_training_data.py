#!/usr/bin/env python3
"""
Filter training data to remove low-quality pairs.

Removes:
1. MCQ-style responses (A. B. C. D. format)
2. Long responses without any source citations
3. Responses with HTML entities in questions (LOINC coded terms)
4. Responses shorter than a minimum threshold

Usage:
    python scripts/filter_training_data.py \
        --input training_runs/.../training_data.jsonl \
        --output training_runs/.../training_data_filtered.jsonl
"""

import argparse
import json
import re
import sys


def is_mcq_style(response: str) -> bool:
    """Detect MCQ-format responses."""
    # Multiple choice markers
    mc_patterns = [
        r'\bA\.\s', r'\bB\.\s', r'\bC\.\s', r'\bD\.\s',
        r'\(a\)\s', r'\(b\)\s', r'\(c\)\s', r'\(d\)\s',
        r'correct answer is',
    ]
    matches = sum(1 for p in mc_patterns if re.search(p, response))
    return matches >= 3  # At least 3 MC markers


def has_loinc_coded_question(instruction: str) -> bool:
    """Detect LOINC/coded term questions with pipe-separated fields."""
    return bool(re.search(r'&#x7[A-F0-9];|ANYProp|ANYTm|ANYSys|ANYMeth', instruction))


def has_citations(response: str) -> bool:
    """Check if response contains source citations."""
    return bool(re.search(r'\[Source\s*\d+\]|\[Source\]|According to', response))


def is_fabrication_risk(response: str) -> bool:
    """Detect long uncited responses that may be fabricated."""
    return len(response) > 800 and not has_citations(response)


def main():
    parser = argparse.ArgumentParser(description="Filter training data")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--min-length", type=int, default=200,
                        help="Minimum response length (default: 200)")
    args = parser.parse_args()

    total = 0
    kept = 0
    removed = {"mcq": 0, "loinc": 0, "fabrication": 0, "short": 0}

    with open(args.input) as fin, open(args.output, "w") as fout:
        for line in fin:
            total += 1
            row = json.loads(line)
            instruction = row.get("instruction", "")
            response = row.get("response", "")

            if is_mcq_style(response):
                removed["mcq"] += 1
                continue

            if has_loinc_coded_question(instruction):
                removed["loinc"] += 1
                continue

            if is_fabrication_risk(response):
                removed["fabrication"] += 1
                continue

            if len(response) < args.min_length:
                removed["short"] += 1
                continue

            kept += 1
            fout.write(line)

    print(f"Total: {total}")
    print(f"Kept: {kept} ({kept/total*100:.1f}%)")
    print(f"Removed: {total - kept}")
    for reason, count in sorted(removed.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    sys.exit(main())
